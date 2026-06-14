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


def _fill_tracer_columns_with_np_interp(
    z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
):
    """The per-column interpolation that _fill_tracer_columns replaced."""
    for icell in range(z_tilde_mid.shape[1]):
        lo = min_lev[icell]
        hi = max_lev[icell]
        z_mid = z_tilde_mid[0, icell, lo : hi + 1]
        for woa, out in [(woa_ct, ct_out), (woa_sa, sa_out)]:
            col = woa[icell, :]
            out[0, icell, lo : hi + 1] = np.interp(
                z_mid, woa_z[::-1], col[::-1], left=col[-1], right=col[0]
            )


def test_fill_tracer_columns_matches_np_interp(monkeypatch):
    """
    Cell by cell, the chunked interpolation gives exactly what np.interp
    gives, across chunk boundaries, for land and partial columns, for
    heights at, between, above and below the WOA23 levels, and with the
    WOA23 fields passed as the transposed views init_tracers passes.
    """
    # small chunks, so the cells span several of them
    monkeypatch.setitem(
        _fill_tracer_columns.__globals__, '_TRACER_CHUNK_CELLS', 64
    )
    rng = np.random.default_rng(seed=843)
    ncells, nlevels = 300, 20
    woa_z = -np.concatenate([np.arange(0.0, 100.0, 5.0), [150.0, 400.0]])
    nwoa = woa_z.size
    woa_ct = rng.normal(5.0, 3.0, (nwoa, ncells)).T
    woa_sa = rng.normal(35.0, 0.5, (nwoa, ncells)).T

    z_tilde_mid = rng.uniform(-500.0, 10.0, (1, ncells, nlevels))
    # some heights fall exactly on WOA23 levels
    z_tilde_mid[0, :, 0] = rng.choice(woa_z, ncells)
    min_lev = rng.integers(0, 2, ncells)
    max_lev = rng.integers(-1, nlevels, ncells)
    max_lev[:10] = -1

    expected_ct = np.full((1, ncells, nlevels), np.nan)
    expected_sa = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns_with_np_interp(
        z_tilde_mid,
        woa_z,
        woa_ct,
        woa_sa,
        min_lev,
        max_lev,
        expected_ct,
        expected_sa,
    )
    ct_out = np.full((1, ncells, nlevels), np.nan)
    sa_out = np.full((1, ncells, nlevels), np.nan)
    _fill_tracer_columns(
        z_tilde_mid, woa_z, woa_ct, woa_sa, min_lev, max_lev, ct_out, sa_out
    )

    np.testing.assert_array_equal(ct_out, expected_ct)
    np.testing.assert_array_equal(sa_out, expected_sa)


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
