import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical.ztilde import RhoSw
from polaris.tasks.ocean.realistic_global.init.pstar_init import (
    _clamp_geom_z_bot,
    _fill_tracer_columns,
    _geom_z_bot_from_topo,
)


def _sat_column(factor=1.0, nlevels=4, thickness=100.0, ncells=1):
    """
    Return (spec_vol, pseudo_thickness, cell_mask) for a uniform saturated
    column where ``RhoSw * spec_vol == factor`` so the geometric thickness of
    each layer is ``factor * thickness`` and ``D_max = factor * nlevels *
    thickness``.
    """
    spec_vol = xr.DataArray(
        np.full((1, ncells, nlevels), factor / RhoSw),
        dims=['Time', 'nCells', 'nVertLevels'],
    )
    pseudo = xr.DataArray(
        np.full((1, ncells, nlevels), thickness),
        dims=['Time', 'nCells', 'nVertLevels'],
    )
    mask = xr.DataArray(
        np.ones((ncells, nlevels), dtype=bool),
        dims=['nCells', 'nVertLevels'],
    )
    return spec_vol, pseudo, mask


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


def test_clamp_geom_z_bot_deep_shallow_inrange():
    """
    D_max = 400 m, D_min = 300 m (top 3 of 4 layers): a too-deep target is
    limited to -D_max, a too-shallow target is raised to -D_min, and an
    in-range target is unchanged.
    """
    spec_vol, pseudo, mask = _sat_column(ncells=3)  # factor 1 -> D_max = 400
    geom_z_bot = xr.DataArray([-10000.0, -350.0, -1.0], dims=['nCells'])

    clamped = _clamp_geom_z_bot(
        geom_z_bot=geom_z_bot,
        spec_vol=spec_vol,
        pseudo_thickness=pseudo,
        cell_mask=mask,
        min_bottom_depth=10.0,
        min_vert_levels=3,
    )

    assert clamped.values == pytest.approx([-400.0, -350.0, -300.0])


def test_clamp_geom_z_bot_min_bottom_depth_floor():
    """With min_vert_levels=1 the depth floor comes from min_bottom_depth."""
    spec_vol, pseudo, mask = _sat_column()  # top 1 layer -> 100 m
    geom_z_bot = xr.DataArray([-1.0], dims=['nCells'])

    clamped = _clamp_geom_z_bot(
        geom_z_bot=geom_z_bot,
        spec_vol=spec_vol,
        pseudo_thickness=pseudo,
        cell_mask=mask,
        min_bottom_depth=150.0,
        min_vert_levels=1,
    )

    # D_min = max(150, 100) = 150
    assert clamped.values == pytest.approx([-150.0])


def test_clamp_geom_z_bot_density_reduces_dmax():
    """
    A denser column (RhoSw*specVol = 0.9) yields a geometric column shorter
    than its pseudo depth, so D_max = 0.9 * 400 = 360 m.
    """
    spec_vol, pseudo, mask = _sat_column(factor=0.9)
    geom_z_bot = xr.DataArray([-10000.0], dims=['nCells'])

    clamped = _clamp_geom_z_bot(
        geom_z_bot=geom_z_bot,
        spec_vol=spec_vol,
        pseudo_thickness=pseudo,
        cell_mask=mask,
        min_bottom_depth=0.0,
        min_vert_levels=3,
    )

    assert clamped.values == pytest.approx([-360.0])


def test_clamp_geom_z_bot_preserves_attrs():
    """An in-range target is returned unchanged with its attributes intact."""
    spec_vol, pseudo, mask = _sat_column()
    geom_z_bot = xr.DataArray([-350.0], dims=['nCells'], attrs={'units': 'm'})

    clamped = _clamp_geom_z_bot(
        geom_z_bot=geom_z_bot,
        spec_vol=spec_vol,
        pseudo_thickness=pseudo,
        cell_mask=mask,
        min_bottom_depth=10.0,
        min_vert_levels=3,
    )

    assert clamped.attrs.get('units') == 'm'
    assert clamped.values == pytest.approx([-350.0])
