"""
Unit tests for ZTildeInitStep.

All tests are self-contained: no file I/O, no full Polaris step framework.
A minimal ConfigParser and xarray.Dataset are constructed in each test.
"""

import logging
from configparser import ConfigParser

import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import RhoSw
from polaris.ocean.vertical.ztilde_init import ZTildeInitStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    rhoref=None, iter_count=10, partial_cell_type=None, bottom_depth=600.0
):
    """Return a minimal ConfigParser for ZTildeInitStep tests.

    Parameters
    ----------
    bottom_depth : float
        Reference pseudo-depth of the grid (m).  Must be >= the target
        geometric depth used in the test so the coordinate is not capped.
    """
    if rhoref is None:
        rhoref = RhoSw

    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', '4')
    # bottom_depth rescales uniform grid from [0,1] to [0, bottom_depth]
    config.set('vertical_grid', 'bottom_depth', str(bottom_depth))
    config.set('vertical_grid', 'min_vert_levels', '1')
    config.set('vertical_grid', 'min_layer_thickness', '0.0')
    config.set('vertical_grid', 'pseudothickness_iter_count', str(iter_count))
    config.set(
        'vertical_grid',
        'water_col_adjust_frac_change_threshold',
        '1e-12',
    )
    if partial_cell_type is not None:
        config.set('vertical_grid', 'partial_cell_type', partial_cell_type)
        config.set('vertical_grid', 'min_pc_fraction', '0.1')

    config.add_section('ocean')
    config.set('ocean', 'eos_type', 'constant')
    config.set('ocean', 'eos_constant_rhoref', str(rhoref))

    return config


def _make_ds_mesh(ncells=1):
    """Return a minimal horizontal mesh dataset with nCells dimension."""
    return xr.Dataset(
        {'xCell': xr.DataArray(np.zeros(ncells), dims=['nCells'])}
    )


def _make_step(cls, config, logger=None):
    """Bypass the Polaris Step constructor and set the bare minimum attrs."""
    step = object.__new__(cls)
    step.config = config
    step.logger = logger or logging.getLogger('test_ztilde_init')
    return step


class _ConstantTracerStep(ZTildeInitStep):
    """Minimal concrete subclass that returns constant CT and SA."""

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        ncells = ds.sizes['nCells']
        nvertlevels = ds.sizes['nVertLevels']
        shape = (1, ncells, nvertlevels)
        ct = xr.DataArray(
            data=np.full(shape, 10.0),
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        sa = xr.DataArray(
            data=np.full(shape, 35.0),
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        return ct, sa


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_abstract_class_not_instantiable():
    """ZTildeInitStep itself cannot be instantiated (init_tracers is abstract).

    The test checks __abstractmethods__ directly so no Polaris component mock
    is needed.
    """
    assert 'init_tracers' in ZTildeInitStep.__abstractmethods__


def test_subclass_without_init_tracers_not_instantiable():
    """A subclass that does not implement init_tracers raises TypeError."""

    class _Missing(ZTildeInitStep):
        pass

    assert 'init_tracers' in _Missing.__abstractmethods__


def test_minimal_subclass_returns_complete_dataset():
    """A constant-tracer subclass completes without error and the returned
    dataset contains all expected base-class output variables.
    """
    config = _make_config()
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -500.0), dims=['nCells'])

    ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    required = [
        'temperature',
        'salinity',
        'SpecVol',
        'pressure',
        'GeomZMid',
        'GeomZInterface',
        'bottomDepth',
        'ssh',
        'SurfacePressure',
        'BottomPressure',
        'PseudoThickness',
        'ZTildeMid',
        'ZTildeInterface',
        'cellMask',
        'minLevelCell',
        'maxLevelCell',
        'RefPseudoThickness',
        'vertCoordMovementWeights',
    ]
    for var in required:
        assert var in ds, f'{var!r} missing from output dataset'


def test_constant_density_converges_cleanly(caplog):
    """With rhoref = RhoSw the initial guess is exact.

    The loop should exit via the convergence check (not a stagnation warning)
    and bottomDepth should equal the target to within floating-point precision.
    """
    target_depth = 500.0
    # bottom_depth == target_depth: reference grid exactly matches the column
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])

    with caplog.at_level(logging.WARNING, logger='test_ztilde_init'):
        ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    # No stagnation warning should appear for a perfect initial guess
    assert 'full-cell snap' not in caplog.text

    bottom_depth = float(ds.bottomDepth.values.flat[0])
    np.testing.assert_allclose(bottom_depth, target_depth, rtol=1e-10)

    # For constant density equal to RhoSw and zero SSP the diagnostic SSH
    # must be exactly zero.
    ssh = float(ds.ssh.values.flat[0])
    np.testing.assert_allclose(ssh, 0.0, atol=1e-10)


def test_wrong_reference_density_requires_multiple_iterations():
    """When rhoref != RhoSw the first iteration produces a non-unit scaling
    factor and multiple iterations are needed before the convergence check
    fires.  The final bottomDepth should match the target to within the
    convergence threshold times the target depth.
    """
    # 1% denser than the reference → scaling ≠ 1 on first iteration
    rhoref = RhoSw * 1.01
    config = _make_config(rhoref=rhoref)
    step = _make_step(_ConstantTracerStep, config)

    target_depth = 500.0
    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])

    ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    bottom_depth = float(ds.bottomDepth.values.flat[0])
    # Converged bottomDepth must be within the fractional threshold of target
    threshold = 1e-12
    np.testing.assert_allclose(bottom_depth, target_depth, rtol=threshold * 10)


def test_nonzero_surface_pressure_shifts_pressures():
    """With non-zero surface pressure the iteration converges to
    SSH = -SP/(RhoSw * Gravity).

    For constant density equal to RhoSw the coordinate converges in two
    iterations. The target SSH is -ssp/(RhoSw*Gravity), so bottomDepth equals
    target_depth - ssp/(RhoSw*Gravity) (the actual water-column thickness
    between the depressed surface and the seafloor).  The reference grid needs
    to reach pseudo_bottom_depth = target_depth (not target_depth +
    ssp/(RhoSw*Gravity)) because the SP terms cancel in the initial BP.
    """
    from polaris.ocean.vertical.ztilde import Gravity, RhoSw

    target_depth = 500.0
    # ~1 m of water-column pressure (well below the 500 m column)
    ssp = RhoSw * Gravity * 1.0

    # bottom_depth must cover pseudo_bottom_depth ≈ target_depth (SP terms
    # cancel in the initial BP so the pseudo-column stays within target_depth).
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])
    surface_pressure = xr.DataArray(np.full(ncells, ssp), dims=['nCells'])

    ds = step.run_z_tilde_init(
        ds_mesh, geom_z_bot, surface_pressure=surface_pressure
    )

    sp_out = float(ds.SurfacePressure.values.flat[0])
    np.testing.assert_allclose(sp_out, ssp, rtol=1e-12)

    bp_out = float(ds.BottomPressure.values.flat[0])
    assert bp_out > sp_out, 'BottomPressure must exceed SurfacePressure'

    # SSH equals the surface-pressure depression −SP/(ρ₀g).
    expected_ssh = -ssp / (RhoSw * Gravity)
    ssh = float(ds.ssh.values.flat[0])
    np.testing.assert_allclose(ssh, expected_ssh, rtol=1e-10)

    # bottomDepth is the actual water column: SSH − geom_z_bot.
    expected_bottom_depth = expected_ssh - float(geom_z_bot.values.flat[0])
    bottom_depth = float(ds.bottomDepth.values.flat[0])
    np.testing.assert_allclose(bottom_depth, expected_bottom_depth, rtol=1e-10)


def test_surface_pressure_sets_ztilde_surface_correctly():
    """With non-zero surface pressure the top ZTildeInterface should be
    -SurfacePressure / (RhoSw * Gravity), not zero.

    This is the invariant that reference.py relies on: it computes
    z_tilde_surf = -surface_pressure / (RhoSw * Gravity) and expects the
    z-tilde grid to start there.  If the surface is stuck at zero the tracer
    interpolation in init_tracers (which uses ZTildeMid) and the reference
    solution will be offset from each other.
    """
    from polaris.ocean.vertical.ztilde import Gravity, RhoSw

    target_depth = 500.0
    ssp = RhoSw * Gravity * 1.0  # ~1 m water-column equivalent
    # bottom_depth = target_depth: SP terms cancel in the initial BP so
    # pseudo_bottom_depth stays at target_depth.
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])
    surface_pressure = xr.DataArray(np.full(ncells, ssp), dims=['nCells'])

    ds = step.run_z_tilde_init(
        ds_mesh, geom_z_bot, surface_pressure=surface_pressure
    )

    expected_z_tilde_surf = -ssp / (RhoSw * Gravity)
    z_tilde_top = float(
        ds.ZTildeInterface.isel(Time=0, nCells=0, nVertLevelsP1=0).values
    )
    np.testing.assert_allclose(z_tilde_top, expected_z_tilde_surf, rtol=1e-10)


def test_surface_pressure_total_pseudo_thickness():
    """The sum of PseudoThickness should equal
    (BottomPressure - SurfacePressure)/ (RhoSw * Gravity).

    This verifies that the z-star-style scaling scale = (BP - SP) / BP in
    init_z_tilde_vertical_coord is applied correctly.  A wrong scaling
    produces pseudo-thicknesses that don't span the right range, which
    corrupts the ZTildeMid values used in tracer interpolation without causing
    an obvious convergence failure.
    """
    from polaris.ocean.vertical.ztilde import Gravity, RhoSw

    target_depth = 500.0
    ssp = RhoSw * Gravity * 1.0
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])
    surface_pressure = xr.DataArray(np.full(ncells, ssp), dims=['nCells'])

    ds = step.run_z_tilde_init(
        ds_mesh, geom_z_bot, surface_pressure=surface_pressure
    )

    total_pseudo = float(
        ds.PseudoThickness.isel(Time=0, nCells=0).sum().values
    )
    bp = float(ds.BottomPressure.isel(nCells=0).values)
    sp = float(ds.SurfacePressure.isel(nCells=0).values)
    expected = (bp - sp) / (RhoSw * Gravity)
    np.testing.assert_allclose(total_pseudo, expected, rtol=1e-10)


def test_two_cell_surface_pressure_gradient():
    """Two cells with different surface pressures each converge to
    ssh[i] = −SP[i]/(ρ₀g) and bottomDepth[i] = ssh[i] − geom_z_bot.
    Each cell's ZTildeInterface top equals ssh[i].

    This directly mimics the surface_pressure_gradient.cfg geometry and
    exercises the default _build_vert_coord_ds path with a per-cell surface
    pressure vector.
    """
    from polaris.ocean.vertical.ztilde import Gravity, RhoSw

    target_depth = 500.0
    ssp_mid = RhoSw * Gravity * 10.0  # ~10 m water-column equivalent
    ssp_grad = RhoSw * Gravity * 1.0  # ~1 m/cell gradient
    ssp = np.array([ssp_mid - ssp_grad, ssp_mid + ssp_grad])

    # SP terms cancel in the initial BP; pseudo_bottom_depth ≈ target_depth.
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 2
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])
    surface_pressure = xr.DataArray(ssp, dims=['nCells'])

    ds = step.run_z_tilde_init(
        ds_mesh, geom_z_bot, surface_pressure=surface_pressure
    )

    for i in range(ncells):
        expected_ssh = -ssp[i] / (RhoSw * Gravity)
        expected_bottom_depth = expected_ssh - float(
            geom_z_bot.isel(nCells=i).values
        )

        ssh = float(ds.ssh.isel(nCells=i).values)
        np.testing.assert_allclose(
            ssh,
            expected_ssh,
            rtol=1e-10,
            err_msg=f'cell {i} ssh',
        )
        bottom_depth = float(ds.bottomDepth.isel(nCells=i).values)
        np.testing.assert_allclose(
            bottom_depth,
            expected_bottom_depth,
            rtol=1e-10,
            err_msg=f'cell {i} bottomDepth',
        )
        zt_surf = float(
            ds.ZTildeInterface.isel(Time=0, nCells=i, nVertLevelsP1=0).values
        )
        np.testing.assert_allclose(
            zt_surf,
            expected_ssh,
            rtol=1e-10,
            err_msg=f'cell {i} ZTildeInterface top',
        )


def test_full_cell_stagnation_warning_and_early_exit(caplog):
    """When _build_vert_coord_ds always returns the same BottomPressure
    (simulating full-cell snapping) the stagnation check should fire and the
    loop should stop with a warning, without raising an exception.
    """

    class _StagnantStep(_ConstantTracerStep):
        """Override _build_vert_coord_ds to snap to a fixed pressure."""

        def _build_vert_coord_ds(
            self,
            ds_mesh: xr.Dataset,
            bottom_pressure: xr.DataArray,
            surface_pressure: xr.DataArray | None = None,
        ) -> xr.Dataset:
            # Call the real coord builder once to get a properly structured ds
            ds = super()._build_vert_coord_ds(
                ds_mesh, bottom_pressure, surface_pressure
            )
            # Then hard-code BottomPressure to a fixed value regardless of
            # the incoming bottom_pressure (full-cell snapping simulation)
            fixed_pressure = xr.DataArray(
                np.full(ds_mesh.sizes['nCells'], 5.0e6),
                dims=['nCells'],
            )
            ds['BottomPressure'] = fixed_pressure
            return ds

    config = _make_config(iter_count=10)
    step = _make_step(_StagnantStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -500.0), dims=['nCells'])

    with caplog.at_level(logging.WARNING, logger='test_ztilde_init'):
        ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    assert 'full-cell snap' in caplog.text
    # Must still return a usable dataset
    assert 'bottomDepth' in ds
