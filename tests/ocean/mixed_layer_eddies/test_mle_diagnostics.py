import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.config import PolarisConfigParser
from polaris.mesh.reconstruct import build_reconstruction_weights
from polaris.mesh.vector import compute_edge_normal_vec
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    Gravity,
    RhoSw,
    compute_buoyancy_gradient,
    compute_eddy_overturning,
    compute_fk11_stream_function,
    compute_mixed_layer_n2,
    compute_model_stream_function,
    compute_mu,
    compute_potential_energy,
    fit_mu_amplitude,
    get_consistent_edges,
    get_frontal_cell_mask,
    get_frontal_lines,
)
from polaris.tasks.ocean.mixed_layer_eddies.flux import compute_combined_flux

DC = 1000.0
CORIOLIS = 1.4e-4
THICKNESS = 2.0
NLEVELS = 30


@pytest.fixture(scope='module')
def config():
    """The config options of the mixed-layer eddies tasks"""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.mixed_layer_eddies', 'mixed_layer_eddies.cfg'
    )
    return config


@pytest.fixture(scope='module')
def ds_mesh():
    """A small doubly periodic planar hex mesh on an f-plane"""
    ds = make_planar_hex_mesh(
        nx=8, ny=40, dc=DC, nonperiodic_x=False, nonperiodic_y=False
    )
    ds['fCell'] = CORIOLIS * xr.ones_like(ds.xCell)
    ds['fEdge'] = CORIOLIS * xr.ones_like(ds.xEdge)
    return ds


def _uniform_thickness(ds_mesh):
    """Layers of uniform thickness"""
    return THICKNESS * xr.ones_like(ds_mesh.xCell).expand_dims(
        nVertLevels=NLEVELS, axis=1
    )


def _density_to_salinity(config, density):
    """Invert the salinity-only linear equation of state"""
    section = config['ocean']
    rhoref = section.getfloat('eos_linear_rhoref')
    beta = section.getfloat('eos_linear_beta')
    return (density - rhoref) / beta


def test_mu_vanishes_at_the_surface_and_below_the_mixed_layer():
    ml_depth = 30.0
    z = np.array([0.0, -15.0, -30.0, -45.0])
    mu = compute_mu(z, ml_depth)
    np.testing.assert_allclose(mu, [0.0, 1.0, 0.0, 0.0], atol=1e-12)


def test_combined_flux_separates_covariance_and_parameterized_transport(
    config, ds_mesh
):
    """Mean vertical flow is excluded; only the eddy contribution scales."""
    ds = xr.Dataset()
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    ds['ssh'] = xr.zeros_like(ds_mesh.xCell)
    ds['dThreshMLD'] = 24.0 + 1.0e-4 * ds_mesh.yCell
    depth = (np.arange(NLEVELS) + 0.5) * THICKNESS
    phase = 2.0 * np.pi * ds_mesh.xCell / ds_mesh.attrs['x_period']
    perturbation = np.sin(phase)
    b_vertical = xr.DataArray(
        -1.0e-7 * depth - (1.0e-4 - 1.0e-7) * np.maximum(depth - 30.0, 0.0),
        dims='nVertLevels',
    )
    buoyancy = (
        b_vertical + 1.0e-7 * ds_mesh.yCell + 1.0e-4 * perturbation
    ).transpose('nCells', 'nVertLevels')
    ds['salinity'] = _density_to_salinity(
        config, RhoSw * (1.0 - buoyancy / Gravity)
    )
    ds['temperature'] = xr.zeros_like(ds.salinity)
    ds['vertVelocityTop'] = (3.0 + 2.0 * perturbation).expand_dims(
        nVertLevelsP1=NLEVELS + 1, axis=1
    )
    cells = ds_mesh.cellsOnEdge.values - 1
    grad_b = (
        buoyancy.values[cells[:, 1], 0] - buoyancy.values[cells[:, 0], 0]
    ) / ds_mesh.dcEdge.values
    z = -np.arange(NLEVELS + 1) * THICKNESS
    psi = -1.0e6 * grad_b[:, None] * compute_mu(z, 30.0)
    ds['normalMLEvelocity'] = (
        ('nEdges', 'nVertLevels'),
        np.diff(psi, axis=1) / THICKNESS,
    )
    stencil, weights = build_reconstruction_weights(ds_mesh, 'cell')
    first = compute_combined_flux(
        config, ds_mesh, ds, stencil, weights, mle_enabled=True
    )
    np.testing.assert_allclose(first['resolved_flux'], 1.0e-4, rtol=1.0e-8)
    assert first['parameterized_flux'] > 0.0
    mask = get_frontal_cell_mask(ds_mesh, 0.125)
    expected_depth = float(
        ds.dThreshMLD.where(mask).weighted(ds_mesh.areaCell).mean()
    )
    assert first['mixed_layer_depth'] == pytest.approx(expected_depth)
    ds['normalMLEvelocity'] *= 2.0
    ds['vertVelocityTop'] = ds['vertVelocityTop'] + 10.0
    second = compute_combined_flux(
        config, ds_mesh, ds, stencil, weights, mle_enabled=True
    )
    np.testing.assert_allclose(
        second['resolved_flux'], first['resolved_flux'], rtol=1.0e-10
    )
    np.testing.assert_allclose(
        second['parameterized_flux'], 2.0 * first['parameterized_flux']
    )
    np.testing.assert_allclose(
        second['combined_flux'],
        first['resolved_flux'] + 2.0 * first['parameterized_flux'],
    )
    disabled = compute_combined_flux(
        config, ds_mesh, ds, stencil, weights, mle_enabled=False
    )
    assert disabled['parameterized_flux'] == 0.0
    assert disabled['combined_flux'] == disabled['resolved_flux']
    np.testing.assert_allclose(
        disabled['resolved_flux'], first['resolved_flux'], rtol=1.0e-10
    )
    without_eddy_velocity = ds.drop_vars('normalMLEvelocity')
    absent = compute_combined_flux(
        config,
        ds_mesh,
        without_eddy_velocity,
        stencil,
        weights,
        mle_enabled=False,
    )
    assert absent == disabled
    with pytest.raises(ValueError, match='requires normalMLEvelocity'):
        compute_combined_flux(
            config,
            ds_mesh,
            without_eddy_velocity,
            stencil,
            weights,
            mle_enabled=True,
        )
    with pytest.raises(ValueError, match='requires model mixed-layer depth'):
        compute_combined_flux(
            config,
            ds_mesh,
            ds.drop_vars('dThreshMLD'),
            stencil,
            weights,
            mle_enabled=False,
        )


def test_fit_recovers_the_amplitude_of_mu():
    ml_depth = 30.0
    z = np.linspace(0.0, -45.0, 46)
    psi = 3.5 * compute_mu(z, ml_depth)
    assert fit_mu_amplitude(psi, z, ml_depth) == pytest.approx(3.5)


def test_frontal_lines_span_the_domain_in_the_frontal_zone(ds_mesh):
    lines = get_frontal_lines(ds_mesh, 0.125)
    y_period = ds_mesh.attrs['y_period']
    # 40 rows, so 10 row boundaries within a quarter of the domain
    assert len(lines) == 10
    for line in lines:
        assert abs(line.attrs['value'] - 0.5 * y_period) < 0.125 * y_period
        assert line.attrs['length'] == pytest.approx(ds_mesh.attrs['x_period'])


def test_layered_uniform_flow_has_no_eddy_overturning(config, ds_mesh):
    """
    Salinity classes that coincide with layers carry the Eulerian-mean
    transport, so the residual and Eulerian overturning agree
    """
    normal = compute_edge_normal_vec(ds_mesh)
    speed = xr.DataArray(
        np.linspace(0.1, -0.1, NLEVELS), dims=('nVertLevels',)
    )
    ds = xr.Dataset()
    ds['normalVelocity'] = normal.isel(R3=1) * speed
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    salinity = xr.DataArray(
        30.0 + 0.1 * np.arange(NLEVELS), dims=('nVertLevels',)
    )
    ds['salinity'] = xr.ones_like(ds_mesh.xCell) * salinity
    ds['temperature'] = xr.zeros_like(ds.salinity)

    lines = get_frontal_lines(ds_mesh, 0.125)
    bins = np.arange(29.975, 33.0, 0.05)
    ds_psi = compute_eddy_overturning(lines, [ds, ds], bins, config)

    np.testing.assert_allclose(ds_psi.psiEddy, 0.0, atol=1e-12)
    # the residual overturning is not trivially zero
    assert np.abs(ds_psi.psiResidual).max() > 0.1


def _sinusoidal_front(config, ds_mesh, ml_depth, amplitude):
    """
    A vertically uniform mixed layer whose density varies sinusoidally in
    y, over uniform water
    """
    y_period = ds_mesh.attrs['y_period']
    z_mid = -(np.arange(NLEVELS) + 0.5) * THICKNESS
    in_ml = xr.DataArray(z_mid > -ml_depth, dims=('nVertLevels',))
    y_shape = np.sin(2.0 * np.pi * ds_mesh.yCell / y_period)
    density = 1020.0 + (amplitude * y_shape).where(in_ml, 0.0)
    ds = xr.Dataset()
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    ds['salinity'] = _density_to_salinity(config, density).transpose(
        'nCells', 'nVertLevels'
    )
    ds['temperature'] = xr.zeros_like(ds.salinity)
    return ds, density.transpose('nCells', 'nVertLevels')


def test_fk11_formula_for_a_sinusoidal_front(config, ds_mesh):
    """
    With a vertically uniform mixed layer of depth H, the mixed-layer mean
    of the gradient over interfaces down to the top of the first layer
    below H is 30/31 of the gradient within the layer, and the formula
    gives Ce (Ds / Lf) H^2 grad mu(z) / |f| on each edge
    """
    ml_depth = 30.0
    amplitude = 0.05
    ds, density = _sinusoidal_front(config, ds_mesh, ml_depth, amplitude)
    mld = ml_depth * xr.ones_like(ds_mesh.xCell)
    n2_top = xr.zeros_like(ds.salinity)
    edges = np.arange(ds_mesh.sizes['nEdges'])

    psi = compute_fk11_stream_function(
        config,
        ds_mesh,
        ds,
        edges,
        mld,
        n2_top,
        'mixed_layer_eddies_mle',
        'mpas-ocean',
    )

    section = config['mixed_layer_eddies_mle']
    ce = section.getfloat('ce')
    lf_min = section.getfloat('lf_min')
    ds_max = section.getfloat('ds_max')
    tau = section.getfloat('tau')
    time_scale = np.sqrt(CORIOLIS**2 + 1.0 / tau**2)
    cells = ds_mesh.cellsOnEdge.values - 1
    surface_density = density.isel(nVertLevels=0).values
    grad = (
        (Gravity / RhoSw)
        * (surface_density[cells[:, 1]] - surface_density[cells[:, 0]])
        / DC
    )
    grad_ml = grad * 30.0 / 31.0
    frontal_width = np.maximum(
        lf_min, np.abs(grad_ml) * ml_depth / time_scale**2
    )
    z_inter = -np.arange(NLEVELS + 1) * THICKNESS
    expected = (
        ce
        * (min(DC, ds_max) / frontal_width)[:, np.newaxis]
        * ml_depth**2
        * grad_ml[:, np.newaxis]
        * compute_mu(z_inter, ml_depth)[np.newaxis, :]
        / time_scale
    )
    np.testing.assert_allclose(psi, expected, rtol=1e-6, atol=1e-12)


def test_model_stream_function_inverts_the_eddy_velocity(config, ds_mesh):
    """
    The stream function recovered from an eddy velocity defined as the
    models define it is the one it came from, and the mixed-layer depth that
    shaped it is consistent with it while another is not
    """
    ml_depth = 30.0
    ds, _ = _sinusoidal_front(config, ds_mesh, ml_depth, 0.05)
    mld = ml_depth * xr.ones_like(ds_mesh.xCell)
    n2_top = xr.zeros_like(ds.salinity)
    edges = np.arange(ds_mesh.sizes['nEdges'])
    psi = compute_fk11_stream_function(
        config,
        ds_mesh,
        ds,
        edges,
        mld,
        n2_top,
        'mixed_layer_eddies_mle',
        'mpas-ocean',
    )
    eddy_velocity = xr.DataArray(
        -(psi[:, :-1] - psi[:, 1:]) / THICKNESS,
        dims=('nEdges', 'nVertLevels'),
    )

    recovered = compute_model_stream_function(
        config, ds_mesh, ds, edges, eddy_velocity
    )
    np.testing.assert_allclose(recovered, psi, atol=1e-12)

    has_velocity = np.abs(psi).max(axis=1) > 0.0
    consistent = get_consistent_edges(
        config, ds_mesh, ds, edges, eddy_velocity, mld, 'mpas-ocean'
    )
    np.testing.assert_array_equal(consistent, has_velocity)
    inconsistent = get_consistent_edges(
        config, ds_mesh, ds, edges, eddy_velocity, 0.5 * mld, 'mpas-ocean'
    )
    assert not inconsistent.any()


def test_potential_energy_of_uniform_columns(config, ds_mesh):
    ds = xr.Dataset()
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    ds['salinity'] = 30.0 * xr.ones_like(ds.layerThickness)
    ds['temperature'] = xr.zeros_like(ds.salinity)
    rho = 992.565 + 1.0275 * 30.0
    z_mid = -(np.arange(NLEVELS) + 0.5) * THICKNESS
    expected = Gravity * rho * np.sum(z_mid * THICKNESS)
    pe = compute_potential_energy(config, ds_mesh, ds)
    assert float(pe) == pytest.approx(expected, rel=1e-12)


def test_mixed_layer_stratification_of_a_linear_profile(config, ds_mesh):
    drho_dz = -0.01
    z_mid = -(np.arange(NLEVELS) + 0.5) * THICKNESS
    density = 1020.0 + drho_dz * xr.DataArray(z_mid, dims=('nVertLevels',))
    ds = xr.Dataset()
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    ds['salinity'] = _density_to_salinity(config, density) * xr.ones_like(
        ds.layerThickness
    )
    ds['temperature'] = xr.zeros_like(ds.salinity)
    cell_mask = get_frontal_cell_mask(ds_mesh, 0.125)
    n2 = compute_mixed_layer_n2(config, ds_mesh, ds, cell_mask, 30.0)
    assert float(n2) == pytest.approx(-(Gravity / RhoSw) * drho_dz)


def test_buoyancy_gradient_of_a_sinusoidal_front(config, ds_mesh):
    y_period = ds_mesh.attrs['y_period']
    amplitude = 0.05
    y_shape = np.sin(2.0 * np.pi * ds_mesh.yCell / y_period)
    density = 1020.0 + amplitude * y_shape * xr.ones_like(
        _uniform_thickness(ds_mesh)
    )
    ds = xr.Dataset()
    ds['layerThickness'] = _uniform_thickness(ds_mesh)
    ds['salinity'] = _density_to_salinity(config, density)
    ds['temperature'] = xr.zeros_like(ds.salinity)
    cell_mask = get_frontal_cell_mask(ds_mesh, 0.125)
    gradient = compute_buoyancy_gradient(config, ds_mesh, ds, cell_mask, 30.0)
    # the derivative of the sine averaged over the frontal zone
    half_width = 0.125 * y_period
    expected = (
        -(Gravity / RhoSw)
        * amplitude
        * (
            np.sin(2.0 * np.pi * (0.5 * y_period + half_width) / y_period)
            - np.sin(2.0 * np.pi * (0.5 * y_period - half_width) / y_period)
        )
        / (2.0 * half_width)
    )
    assert float(gradient) == pytest.approx(expected, rel=0.05)
