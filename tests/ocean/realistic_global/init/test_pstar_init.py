import logging

import gsw
import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.realistic_global.init.pstar_init import (
    RealisticPStarInitStep,
    _clamp_geom_z_bot,
    _fill_tracer_columns,
    _geom_z_bot_from_topo,
    _ice_covered_thickness,
    add_land_ice_fields,
    compute_land_ice_load,
    estimate_level_count,
    fill_thin_film_tracers,
    shorten_loaded_columns,
)

DRAFT_DENSITY = 1028.0
FILM_LAYER_THICKNESS = 0.05


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


def _make_topo_ds(base_elevations, ocean_base_elevations):
    """
    Return a minimal topo dataset with the base elevation (m) over the whole
    cell and over its ocean part
    """
    return xr.Dataset(
        data_vars={
            'base_elevation': (
                ['nCells'],
                np.array(base_elevations, dtype=float),
                {'long_name': 'base elevation', 'units': 'm'},
            ),
            'ocean_masked_base_elevation': (
                ['nCells'],
                np.array(ocean_base_elevations, dtype=float),
                {'long_name': 'base elevation', 'units': 'm'},
            ),
        }
    )


def test_geom_z_bot_from_topo_without_ocean_is_sea_level():
    ds_topo = _make_topo_ds([-100.0, 1400.0], [-100.0, np.nan])
    geom_z_bot = _geom_z_bot_from_topo(ds_topo)
    assert geom_z_bot.values == pytest.approx([-100.0, 0.0])


def test_geom_z_bot_from_topo_is_the_ocean_mean():
    # the last cell holds land, so its mean over the whole cell is above sea
    # level, but its ocean part is not
    ds_topo = _make_topo_ds([-100.0, -500.0, 180.0], [-100.0, -500.0, -40.0])
    geom_z_bot = _geom_z_bot_from_topo(ds_topo)

    assert geom_z_bot.dims == ('nCells',)
    assert geom_z_bot.values == pytest.approx([-100.0, -500.0, -40.0])
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


def test_filling_holes_caps_a_hole_and_returns():
    """A hole that the re-solve removes ends the loop without an error."""
    step = _StubPStarInitStep(hole_persists=False)

    ds_out = step._run_pstar_init_filling_holes(
        _line_mesh(), xr.DataArray([-300.0, -500.0, -300.0], dims='nCells')
    )

    assert ds_out.maxLevelCell.values.tolist() == [3, 3, 3]
    # the hole's seafloor is capped at the bottom of its neighbors' level
    assert step.geom_z_bots[-1].values == pytest.approx([-300.0] * 3)


def test_filling_holes_raises_if_holes_remain():
    """Holes that survive every pass are an error, not a warning."""
    step = _StubPStarInitStep(hole_persists=True)

    with pytest.raises(ValueError, match='Bathymetry holes'):
        step._run_pstar_init_filling_holes(
            _line_mesh(),
            xr.DataArray([-300.0, -500.0, -300.0], dims='nCells'),
        )


class _StubPStarInitStep(RealisticPStarInitStep):
    """
    A p-star init step whose solve is a stub: the middle of three cells
    reaches level 5 while its neighbors stop at level 3, unless its target
    seafloor has been raised to theirs and ``hole_persists`` is False.
    Interfaces are every 100 m, so level k's bottom is at -100 k.
    """

    def __init__(self, hole_persists, config=None):
        self.logger = logging.getLogger('test')
        self.hole_persists = hole_persists
        self.geom_z_bots = []
        self.sea_surface_heights = []
        self.config = config
        self._thin_film = None

    def run_pstar_init(
        self,
        ds_mesh,
        geom_z_bot,
        surface_pressure=None,
        sea_surface_height=None,
    ):
        self.geom_z_bots.append(geom_z_bot)
        self.sea_surface_heights.append(sea_surface_height)
        filled = float(geom_z_bot.values[1]) > -301.0
        if filled and not self.hole_persists:
            max_level_cell = [3, 3, 3]
        else:
            max_level_cell = [3, 5, 3]
        geom_z_interface = -100.0 * np.tile(np.arange(6.0), (1, 3, 1))
        return xr.Dataset(
            data_vars={
                'maxLevelCell': (['nCells'], np.array(max_level_cell)),
                'minLevelCell': (['nCells'], np.ones(3, dtype=int)),
                'SurfacePressure': (
                    ['nCells'],
                    np.zeros(3)
                    if surface_pressure is None
                    else np.asarray(surface_pressure),
                ),
                # the stub's seafloor is always representable
                'bottomDepth': (['nCells'], -np.asarray(geom_z_bot)),
                'GeomZInterface': (
                    ['Time', 'nCells', 'nVertLevelsP1'],
                    geom_z_interface,
                ),
            }
        )


def _line_mesh():
    """Return a mesh of three cells in a line, each the next's neighbor."""
    return xr.Dataset(
        data_vars={
            'cellsOnCell': (
                ['nCells', 'maxEdges'],
                np.array([[2, 0], [1, 3], [2, 0]]),
            ),
            'nEdgesOnCell': (['nCells'], np.array([1, 2, 1])),
        }
    )


# --- ice-shelf cavities ---


def test_estimate_level_count():
    interfaces = np.array([0.0, 10.0, 30.0, 60.0, 100.0])
    count = estimate_level_count(
        interfaces=interfaces,
        bottom_depth=np.array([5.0, 35.0, 1000.0]),
        min_vert_levels=2,
    )
    # at least the minimum, and at most every level
    assert count.tolist() == [2, 3, 4]


def _load(pressure, bottom_depth, level_count):
    return compute_land_ice_load(
        land_ice_pressure=xr.DataArray(pressure, dims='nCells'),
        geom_z_bot=xr.DataArray(-np.asarray(bottom_depth), dims='nCells'),
        level_count=np.asarray(level_count),
        thin_film_layer_thickness=FILM_LAYER_THICKNESS,
        draft_density=DRAFT_DENSITY,
    )


def test_land_ice_load_floats_light_ice():
    # 400 m of draft over a 1000 m bed floats
    pressure = DRAFT_DENSITY * Gravity * 400.0
    surface_pressure, ssh, film = _load(
        [0.0, pressure], [1000.0] * 2, [40] * 2
    )
    assert surface_pressure.values == pytest.approx([0.0, pressure])
    assert ssh.values == pytest.approx([0.0, -400.0])
    assert not film.values.any()


def test_land_ice_load_caps_heavy_ice_on_a_thin_film():
    # grounded ice, and floating ice that leaves too thin a column, are both
    # capped at the pressure under which they float on the thin film
    bottom_depth = np.array([300.0, 300.0])
    level_count = np.array([30, 30])
    heavy = DRAFT_DENSITY * Gravity * 2000.0
    nearly = DRAFT_DENSITY * Gravity * 299.0
    surface_pressure, ssh, film = _load(
        [heavy, nearly], bottom_depth, level_count
    )
    film_thickness = FILM_LAYER_THICKNESS * level_count
    assert ssh.values == pytest.approx(-bottom_depth + film_thickness)
    assert surface_pressure.values == pytest.approx(
        DRAFT_DENSITY * Gravity * (bottom_depth - film_thickness)
    )
    assert film.values.all()


def _freeze_config():
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean.ice_shelf', 'freeze.cfg')
    config.set('ocean', 'model', 'mpas-ocean')
    return config


def test_thin_film_tracers_are_fresh_at_the_freezing_point():
    ct = xr.DataArray(
        np.array([[[1.0, 2.0, np.nan], [1.0, 2.0, 3.0]]]),
        dims=('Time', 'nCells', 'nVertLevels'),
        attrs={'units': 'degC'},
    )
    sa = xr.full_like(ct, 34.0).where(ct.notnull())
    film = xr.DataArray([1, 0], dims='nCells')
    pressure = xr.DataArray([2.0e7, 0.0], dims='nCells')
    config = _freeze_config()

    ct_out, sa_out = fill_thin_film_tracers(config, ct, sa, film, pressure)

    freezing_pt = 6.22e-2 - 7.43e-8 * 2.0e7
    expected_ct = gsw.CT_from_pt(0.0, freezing_pt)
    assert ct_out.values[0, 0, :2] == pytest.approx([expected_ct] * 2)
    assert sa_out.values[0, 0, :2] == pytest.approx([0.0, 0.0])
    # below the seafloor stays undefined, and other columns are unchanged
    assert np.isnan(ct_out.values[0, 0, 2])
    assert ct_out.values[0, 1].tolist() == [1.0, 2.0, 3.0]
    assert sa_out.values[0, 1].tolist() == [34.0] * 3
    assert ct_out.dims == ct.dims
    assert ct_out.attrs == ct.attrs


def test_land_ice_fields():
    ds_topo = xr.Dataset(
        {
            'landIceMask': ('nCells', [0, 1, 1]),
            # the second cell is half land, and its ocean is all under ice
            'ocean_frac': ('nCells', [1.0, 0.5, 1.0]),
            'ocean_masked_ice_frac': ('nCells', [0.2, 0.5, 1.0]),
            'ocean_masked_grounded_frac': ('nCells', [0.0, 0.125, 1.0]),
        }
    )
    ds_out = xr.Dataset({'ssh': (('Time', 'nCells'), [[0.0, -500.0, -9.0]])})
    pressure = xr.DataArray([0.0, 5.0e6, 2.0e7], dims='nCells')
    thin_film = xr.Dataset({'thinFilmMask': ('nCells', [0, 0, 1])})

    ds_out = add_land_ice_fields(ds_out, ds_topo, pressure, thin_film)

    assert ds_out.landIceMask.values.tolist() == [[0, 1, 1]]
    # ice outside the land-ice mask is not land ice, and the fractions are
    # of each cell's ocean part, not of the whole cell
    assert ds_out.landIceFraction.values.tolist() == [[0.0, 1.0, 1.0]]
    assert ds_out.landIceFloatingFraction.values[0] == pytest.approx(
        [0.0, 0.75, 0.0]
    )
    assert ds_out.landIceFloatingMask.values.tolist() == [[0, 1, 0]]
    # the full pressure, which MPAS-Ocean caps itself
    assert ds_out.landIcePressure.values.tolist() == [[0.0, 5.0e6, 2.0e7]]
    assert ds_out.landIceDraft.values.tolist() == [[0.0, -500.0, -9.0]]
    assert ds_out.thinFilmMask.values.tolist() == [[0, 0, 1]]
    for name in ['landIcePressure', 'landIceDraft']:
        assert ds_out[name].dims == ('Time', 'nCells')


def test_ice_covered_thickness_is_the_thickness_of_the_ice_itself():
    # every cell holds 400 m thick ice: over all of its ocean, over a
    # quarter of it (a calving front), and over half of the ocean part of a
    # cell that is half land; the last cell has no ice
    ds_topo = xr.Dataset(
        {
            'ocean_frac': ('nCells', [1.0, 1.0, 0.5, 1.0]),
            'ocean_masked_ice_frac': ('nCells', [1.0, 0.25, 0.25, 0.0]),
            'ocean_masked_ice_thickness': (
                'nCells',
                [400.0, 100.0, 200.0, 0.0],
            ),
        }
    )

    thickness = _ice_covered_thickness(ds_topo)

    assert thickness.values == pytest.approx([400.0, 400.0, 400.0, 0.0])


def test_filling_holes_settles_the_thin_film_layers():
    """
    With cavities, the solve is repeated until the thin film's layers agree
    with the layers the solve gives.
    """
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init', 'init.cfg'
    )
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global', 'cavities.cfg'
    )
    step = _StubPStarInitStep(hole_persists=False, config=config)
    geom_z_bot = xr.DataArray([-300.0, -300.0, -300.0], dims='nCells')
    # the middle cell is under grounded ice
    pressure = xr.DataArray([0.0, 3.0e7, 0.0], dims='nCells')

    step._run_pstar_init_filling_holes(_line_mesh(), geom_z_bot, pressure)

    # the first solve's film takes its layers from the reference grid, and
    # the next one's from the 3 layers the stub gives
    assert len(step.sea_surface_heights) == 2
    ssh = step.sea_surface_heights[-1]
    assert ssh.values == pytest.approx([0.0, -300.0 + 3 * 0.05, 0.0])
    assert step._thin_film is not None
    assert step._thin_film.thinFilmMask.values.tolist() == [0, 1, 0]


def test_shorten_loaded_columns_removes_the_full_reference_layers():
    interfaces = np.array([0.0, 100.0, 200.0, 300.0])
    spec_vol = xr.DataArray(
        np.full((1, 3), 1.0 / RhoSw), dims=('nCells', 'nVertLevels')
    )
    # a column whose bottom pressure reaches 250 m of pseudo-depth, with 3
    # layers, is to keep only 2
    bottom_pressure = xr.DataArray([RhoSw * Gravity * 250.0], dims='nCells')
    raised = shorten_loaded_columns(
        geom_z_bot=xr.DataArray([-120.0], dims='nCells'),
        bottom_pressure=bottom_pressure,
        spec_vol=spec_vol,
        max_level_cell=np.array([3]),
        interfaces=interfaces,
        filled=np.array([2]),
    )
    # 50 m of pseudo-depth below the 200 m interface, plus 1 m of margin
    assert raised.values == pytest.approx([-120.0 + 51.0])
