import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.pstar_init import (
    _fill_tracer_columns,
    _geom_z_bot_from_topo,
)


def _make_topo_ds(base_elevations):
    """Return a minimal topo dataset with base_elevation (negative, m)."""
    return xr.Dataset(
        data_vars={
            'base_elevation': (
                ['nCells'],
                np.array(base_elevations, dtype=float),
                {'long_name': 'base elevation', 'units': 'm'},
            ),
        }
    )


def test_geom_z_bot_from_topo_passthrough():
    ds_topo = _make_topo_ds([-100.0, -500.0, -4000.0])
    geom_z_bot = _geom_z_bot_from_topo(ds_topo)

    assert geom_z_bot.dims == ('nCells',)
    assert geom_z_bot.values == pytest.approx([-100.0, -500.0, -4000.0])
    assert geom_z_bot.attrs['units'] == 'm'


def test_fill_tracer_columns_constant_profile():
    """Constant WOA23 profile should return that constant at every level."""
    ncells, nlevels, ndepths = 2, 4, 5
    woa_z = np.linspace(0, -500.0, ndepths)  # surface to seafloor (negative)
    woa_ct = np.full((ncells, ndepths), 10.0)
    woa_sa = np.full((ncells, ndepths), 34.5)

    z_tilde_mid = np.linspace(-10, -90, nlevels)
    z_tilde_mid = z_tilde_mid[np.newaxis, np.newaxis, :] * np.ones(
        (1, ncells, nlevels)
    )
    min_lev = np.zeros(ncells, dtype=int)
    max_lev = np.full(ncells, nlevels - 1, dtype=int)

    ct_out = np.full((1, ncells, nlevels), np.nan)
    sa_out = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns(
        z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
    )

    assert ct_out == pytest.approx(10.0)
    assert sa_out == pytest.approx(34.5)


def test_fill_tracer_columns_linear_profile():
    """
    Linear CT profile: CT = -z (positive at surface, decreasing downward).
    Interpolation at exact WOA23 levels should return exact values.
    """
    ncells, nlevels = 1, 3
    woa_z = np.array([0.0, -100.0, -200.0, -300.0])
    woa_ct = -woa_z.reshape(1, -1)  # CT = -z (0, 100, 200, 300)
    woa_sa = np.full((1, 4), 35.0)

    query_z = np.array([-50.0, -150.0, -250.0])
    z_tilde_mid = query_z[np.newaxis, np.newaxis, :]  # (1, 1, 3)

    min_lev = np.array([0])
    max_lev = np.array([nlevels - 1])

    ct_out = np.full((1, ncells, nlevels), np.nan)
    sa_out = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns(
        z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
    )

    expected_ct = np.array([50.0, 150.0, 250.0])
    assert ct_out[0, 0, :] == pytest.approx(expected_ct)


def test_fill_tracer_columns_respects_valid_levels():
    """Values outside [min_lev, max_lev] should remain NaN."""
    ncells, nlevels = 1, 5
    woa_z = np.array([0.0, -100.0, -200.0])
    woa_ct = np.full((ncells, 3), 8.0)
    woa_sa = np.full((ncells, 3), 34.0)

    z_tilde_mid = np.linspace(-10, -90, nlevels)[np.newaxis, np.newaxis, :]
    z_tilde_mid = np.broadcast_to(z_tilde_mid, (1, ncells, nlevels)).copy()

    # Only levels 1-3 are valid
    min_lev = np.array([1])
    max_lev = np.array([3])

    ct_out = np.full((1, ncells, nlevels), np.nan)
    sa_out = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns(
        z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
    )

    assert np.isnan(ct_out[0, 0, 0]), 'Level 0 (invalid) should be NaN'
    assert np.isnan(ct_out[0, 0, 4]), 'Level 4 (invalid) should be NaN'
    assert not np.isnan(ct_out[0, 0, 1]), 'Level 1 (valid) should not be NaN'
    assert not np.isnan(ct_out[0, 0, 3]), 'Level 3 (valid) should not be NaN'


def test_fill_tracer_columns_deep_extrapolation():
    """
    Z-tilde levels deeper than the deepest WOA23 level should receive the
    deepest WOA23 value (flat extrapolation).
    """
    ncells, nlevels = 1, 3
    woa_z = np.array([0.0, -100.0, -200.0])  # WOA23 goes to 200 m
    woa_ct = np.array([[20.0, 10.0, 5.0]])  # surface to 200 m
    woa_sa = np.full((ncells, 3), 35.0)

    query_z = np.array([-50.0, -150.0, -400.0])  # last is below WOA23
    z_tilde_mid = query_z[np.newaxis, np.newaxis, :]

    min_lev = np.array([0])
    max_lev = np.array([nlevels - 1])

    ct_out = np.full((1, ncells, nlevels), np.nan)
    sa_out = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns(
        z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
    )

    assert ct_out[0, 0, 2] == pytest.approx(5.0), (
        'Level below WOA23 should use deepest value (5.0)'
    )
