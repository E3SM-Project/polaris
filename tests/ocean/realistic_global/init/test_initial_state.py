import gsw
import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.initial_state import (
    _add_layer_thickness,
    _add_normal_velocity,
    _convert_tracers_mpas_ocean,
)


def _make_pstar_init_ds(ncells=3, nlevels=4):
    """
    Return a minimal synthetic pstar_init dataset for testing.

    All cells are fully active (cellMask all True).
    """
    geom_z_inter = np.zeros((1, ncells, nlevels + 1))
    for k in range(nlevels + 1):
        geom_z_inter[:, :, k] = -10.0 * k  # 10 m layers
    cell_mask = np.ones((1, ncells, nlevels), dtype=bool)
    ct_vals = np.full((1, ncells, nlevels), 10.0)
    sa_vals = np.full((1, ncells, nlevels), 34.5)
    p_vals = np.full((1, ncells, nlevels), 1e5)  # 1e5 Pa = 10 dbar

    return xr.Dataset(
        data_vars={
            'GeomZInterface': (
                ['Time', 'nCells', 'nVertLevelsP1'],
                geom_z_inter,
            ),
            'cellMask': (['Time', 'nCells', 'nVertLevels'], cell_mask),
            'temperature': (
                ['Time', 'nCells', 'nVertLevels'],
                ct_vals,
                {'long_name': 'conservative temperature', 'units': 'degC'},
            ),
            'salinity': (
                ['Time', 'nCells', 'nVertLevels'],
                sa_vals,
                {'long_name': 'absolute salinity', 'units': 'g kg-1'},
            ),
            'pressure': (
                ['Time', 'nCells', 'nVertLevels'],
                p_vals,
                {'long_name': 'sea pressure', 'units': 'Pa'},
            ),
            'SpecVol': (
                ['Time', 'nCells', 'nVertLevels'],
                np.full((1, ncells, nlevels), 1e-3),
            ),
        }
    )


def _make_mesh_ds(ncells=3, nedges=6):
    """Return a minimal synthetic mesh dataset."""
    lons = np.deg2rad(np.linspace(0.0, 60.0, ncells))
    lats = np.deg2rad(np.linspace(-30.0, 30.0, ncells))
    return xr.Dataset(
        data_vars={
            'lonCell': (['nCells'], lons),
            'latCell': (['nCells'], lats),
        }
    )


# -----------------------------------------------------------------------
# _add_layer_thickness
# -----------------------------------------------------------------------


def test_add_layer_thickness_shape():
    ds = _make_pstar_init_ds(ncells=3, nlevels=4)
    ds_out = _add_layer_thickness(ds)
    assert 'restingThickness' in ds_out
    assert 'layerThickness' in ds_out
    assert ds_out['restingThickness'].dims == ('Time', 'nCells', 'nVertLevels')


def test_add_layer_thickness_values():
    """10-m uniform layers -> resting/layer thickness = 10 m everywhere."""
    ds = _make_pstar_init_ds(ncells=2, nlevels=5)
    ds_out = _add_layer_thickness(ds)
    assert ds_out['restingThickness'].values == pytest.approx(10.0)
    assert ds_out['layerThickness'].values == pytest.approx(10.0)


def test_add_layer_thickness_masks_invalid_levels():
    """Levels where cellMask is False should have thickness = 0."""
    ncells, nlevels = 2, 4
    ds = _make_pstar_init_ds(ncells=ncells, nlevels=nlevels)
    # Mark the deepest level as invalid for both cells
    mask = ds['cellMask'].values.copy()
    mask[:, :, -1] = False
    ds['cellMask'] = xr.DataArray(mask, dims=['Time', 'nCells', 'nVertLevels'])
    ds_out = _add_layer_thickness(ds)
    assert ds_out['restingThickness'].values[0, :, -1] == pytest.approx(0.0)
    assert ds_out['restingThickness'].values[0, :, 0] == pytest.approx(10.0)


# -----------------------------------------------------------------------
# _add_normal_velocity
# -----------------------------------------------------------------------


def test_add_normal_velocity_all_zeros():
    ncells, nlevels, nedges = 3, 4, 6
    ds = _make_pstar_init_ds(ncells=ncells, nlevels=nlevels)
    ds_mesh = _make_mesh_ds(ncells=ncells, nedges=nedges)
    ds_mesh['nEdges'] = xr.DataArray(np.arange(nedges), dims=['nEdges'])
    ds_out = _add_normal_velocity(ds, ds_mesh)
    assert 'normalVelocity' in ds_out
    assert ds_out['normalVelocity'].shape == (1, nedges, nlevels)
    assert ds_out['normalVelocity'].values == pytest.approx(0.0)


# -----------------------------------------------------------------------
# _convert_tracers_mpas_ocean
# -----------------------------------------------------------------------


def test_convert_tracers_mpas_ocean_round_trip():
    """
    Convert CT/SA -> pot-T/prac-S and verify against direct GSW calls.
    """
    ncells, nlevels = 2, 3
    ct_in = np.full((1, ncells, nlevels), 5.0)
    sa_in = np.full((1, ncells, nlevels), 34.0)
    p_pa = np.full((1, ncells, nlevels), 5e4)  # 5 dbar

    lon_rad = np.deg2rad(np.array([10.0, 20.0]))
    lat_rad = np.deg2rad(np.array([-10.0, 10.0]))

    ds = xr.Dataset(
        data_vars={
            'temperature': (['Time', 'nCells', 'nVertLevels'], ct_in.copy()),
            'salinity': (['Time', 'nCells', 'nVertLevels'], sa_in.copy()),
            'pressure': (['Time', 'nCells', 'nVertLevels'], p_pa.copy()),
        }
    )
    ds_mesh = xr.Dataset(
        data_vars={
            'lonCell': (['nCells'], lon_rad),
            'latCell': (['nCells'], lat_rad),
        }
    )
    ds_out = _convert_tracers_mpas_ocean(ds, ds_mesh)

    p_dbar = 5.0
    lon_deg = np.rad2deg(lon_rad)
    lat_deg = np.rad2deg(lat_rad)

    for icell in range(ncells):
        sa_val = sa_in[0, icell, 0]
        ct_val = ct_in[0, icell, 0]
        expected_pot_t = gsw.t_from_CT(sa_val, ct_val, p_dbar)
        expected_prac_s = gsw.SP_from_SA(
            sa_val, p_dbar, lon_deg[icell], lat_deg[icell]
        )
        assert ds_out['temperature'].values[0, icell, 0] == pytest.approx(
            expected_pot_t, rel=1e-6
        )
        assert ds_out['salinity'].values[0, icell, 0] == pytest.approx(
            expected_prac_s, rel=1e-6
        )


def test_convert_tracers_mpas_ocean_variable_names_and_units():
    """After conversion the variable long_name and units should be updated."""
    ds = _make_pstar_init_ds(ncells=2, nlevels=3)
    ds_mesh = _make_mesh_ds(ncells=2)
    ds_out = _convert_tracers_mpas_ocean(ds, ds_mesh)

    assert 'potential temperature' in ds_out['temperature'].attrs.get(
        'long_name', ''
    )
    assert 'practical salinity' in ds_out['salinity'].attrs.get(
        'long_name', ''
    )
    assert ds_out['salinity'].attrs.get('units') == 'PSU'
