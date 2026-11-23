"""
Unit tests for :py:mod:`polaris.ocean.vertical.ice_shelf` and for z-star and
p-star columns that start below the surface.

The reference grid in these tests has 10 levels of 100 m, a partial top
level merges into the level below when it keeps less than half of its
level, and a film column is 3 layers of 5 cm.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.ice_shelf import (
    compute_ice_shelf_groups,
    compute_ice_shelf_top_depth,
    weighted_percentile,
)
from polaris.ocean.vertical.pstar import init_pstar_vertical_coord

GRAVITY = get_constant('standard_acceleration_of_gravity')
RHO_SW = get_constant('seawater_density_reference')
FILM = 0.05
FILM_COLUMN = 3 * FILM


def test_groups_join_grounded_cells_to_the_first_shelf_to_reach_them():
    """
    Floating cells 0-1 and 5-6 are two shelves.  Grounded cells 2-4 between
    them join the one that reaches them first, and 3, reached by both at
    once, the lower.  Grounded cells 8-9, which neither reaches, are a shelf
    of their own, and open-water cell 7 is in none.
    """
    cells_on_edge = np.array(
        [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [8, 9]]
    )
    floating = np.zeros(10, dtype=bool)
    floating[[0, 1, 5, 6]] = True
    grounded = np.zeros(10, dtype=bool)
    grounded[[2, 3, 4, 8, 9]] = True

    group = compute_ice_shelf_groups(cells_on_edge, floating, grounded)

    assert group.tolist() == [1, 1, 1, 1, 2, 2, 2, 0, 3, 3]


def test_weighted_percentile_is_the_value_reaching_the_weight():
    values = np.array([4, 2, 1, 3])
    assert weighted_percentile(values, np.ones(4), 20.0) == 1
    assert weighted_percentile(values, np.ones(4), 50.0) == 2
    assert weighted_percentile(values, np.ones(4), 70.0) == 3
    weights = np.array([1.0, 1.0, 10.0, 1.0])
    assert weighted_percentile(values, weights, 70.0) == 1


def test_surface_keeps_every_column_at_the_surface():
    ds_mesh, ssh, bottom, land_ice, film = _strip([0, 250, 450, 650])
    config = _config(top_level='surface')

    top_depth, group = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert top_depth.values.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert group.values.tolist() == [0, 1, 1, 1]


@pytest.mark.parametrize(
    'percentile, inner_top', [(20.0, 250.0), (50.0, 650.0)]
)
def test_front_cells_take_their_own_draft(percentile, inner_top):
    """
    Front cells 1 (draft 250 m, front 1 km long) and 4 (650 m, 4 km) start
    at their own drafts.  The inner cells start at the percentile of the
    front drafts weighted by front length.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 550, 650, 0], dv_edge=[1e3, 1e3, 1e3, 1e3, 4e3]
    )
    config = _config(percentile=percentile, max_rx1=np.inf)

    top_depth, _ = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    np.testing.assert_allclose(
        top_depth.values, [0.0, 250.0, inner_top, inner_top, 650.0, 0.0]
    )


def test_ice_facing_a_shallower_bed_is_not_a_front():
    """
    Cell 1 meets open water whose bed (200 m) is above its draft, so only
    cell 2 is a front, and cell 1 takes the shelf's top depth from it.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 0], bed=[200, 1000, 1000, 1000]
    )
    config = _config(max_rx1=np.inf)

    top_depth, _ = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    np.testing.assert_allclose(top_depth.values, [0.0, 450.0, 450.0, 0.0])


def test_a_front_cell_blends_its_draft_with_its_shelf_by_its_weight():
    """
    The open water next to cell 1 has its bed half a level below a film
    column under the cell's draft, so the front's weight is a half, and the
    cell starts halfway between its draft and its shelf's top depth.  Its
    front is 1 m long, so the shelf's top depth is cell 3's draft.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 350, 450, 0],
        bed=[250 + FILM_COLUMN + 50, 1000, 1000, 1000, 1000],
        dv_edge=[1.0, 1e3, 1e3, 1e3],
    )
    config = _config(max_rx1=np.inf)

    top_depth, _ = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    np.testing.assert_allclose(
        top_depth.values, [0.0, 350.0, 450.0, 450.0, 0.0]
    )


def test_a_thin_column_counts_less_in_its_shelf():
    """
    Cell 1's column is one and a half film columns thick, so its front's
    weight is a half and the median of the front drafts is cell 3's.  Cell
    1 itself must keep 3 levels, so it starts at the surface.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 350, 450, 0],
        bed=[1000, 250 + 1.5 * FILM_COLUMN, 1000, 1000, 1000],
    )
    config = _config(percentile=50.0, max_rx1=np.inf)

    top_depth, _ = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    np.testing.assert_allclose(top_depth.values, [0.0, 0.0, 450.0, 450.0, 0.0])


def test_film_cells_start_at_the_surface():
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 1000 - FILM_COLUMN]
    )
    film[3] = 1
    config = _config(max_rx1=np.inf)

    top_depth, group = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    np.testing.assert_allclose(top_depth.values, [0.0, 250.0, 250.0, 0.0])
    assert group.values.tolist() == [0, 1, 1, 1]


def test_a_steep_edge_gets_the_shallowest_deeper_top_depth():
    """
    Behind a front at 250 m, the shelf starts at 250 m.  At each steep edge,
    the deeper cell then starts at the shallowest deeper top depth that
    brings rx1 to the maximum, with its neighbor at the shelf's top depth.
    """
    drafts = [0, 250, 450, 650]
    ds_mesh, ssh, bottom, land_ice, film = _strip(drafts)
    config = _config(max_rx1=1.0)

    top_depth, _ = compute_ice_shelf_top_depth(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )
    top = top_depth.values

    base = np.array([0.0, 250.0, 250.0, 250.0])
    assert top[1] == base[1]
    for cell, edge in [(2, (1, 2)), (3, (2, 3))]:
        assert top[cell] > base[cell]
        depths = base.copy()
        depths[cell] = top[cell]
        assert _max_rx1(config, ssh, bottom, depths, [edge]) <= 1.0 + 1e-9
        for shallower in np.linspace(base[cell], top[cell] - 0.01, 8):
            depths[cell] = shallower
            assert _max_rx1(config, ssh, bottom, depths, [edge]) > 1.0


def test_z_star_columns_start_at_their_top_depth():
    """
    At 250 m, half of level 2 is left as a partial top level.  At 270 m,
    less than half is left, so it merges into level 3.  950 m is capped so
    the column keeps 3 levels.
    """
    _, ssh, bottom, _, _ = _strip([0, 250, 270, 650])
    config = _config()
    ds = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    top_depth = xr.DataArray([0.0, 250.0, 270.0, 950.0], dims=('nCells',))

    init_vertical_coord(config, ds, top_depth=top_depth)

    assert ds.minLevelCell.values.tolist() == [1, 3, 4, 8]
    resting = ds.restingThickness.isel(Time=0)
    np.testing.assert_allclose(resting.sum('nVertLevels'), bottom)
    np.testing.assert_allclose(
        resting.isel(nCells=1, nVertLevels=2)
        / resting.isel(nCells=1, nVertLevels=3),
        0.5,
    )
    np.testing.assert_allclose(
        resting.isel(nCells=2, nVertLevels=3)
        / resting.isel(nCells=2, nVertLevels=4),
        1.3,
    )
    thickness = ds.layerThickness.isel(Time=0).sum('nVertLevels')
    np.testing.assert_allclose(thickness, ssh + bottom)


def test_z_star_at_the_surface_is_unchanged():
    _, ssh, bottom, _, _ = _strip([0, 250, 650])
    config = _config()
    ds_default = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    ds_zero = ds_default.copy()

    init_vertical_coord(config, ds_default)
    init_vertical_coord(config, ds_zero, top_depth=xr.zeros_like(bottom))

    xr.testing.assert_identical(ds_default, ds_zero)


def test_p_star_columns_start_at_their_top_depth():
    """
    At 625 m, three quarters of level 6 are left as a partial top level.
    """
    config = _config()
    ds = xr.Dataset(
        {
            'BottomPressure': xr.DataArray(
                RHO_SW * GRAVITY * np.array([1000.0, 1000.0]),
                dims=('nCells',),
            ),
            'SurfacePressure': xr.DataArray(
                RHO_SW * GRAVITY * np.array([0.0, 625.0]), dims=('nCells',)
            ),
        }
    )

    init_pstar_vertical_coord(
        config, ds, top_depth=xr.DataArray([0.0, 625.0], dims=('nCells',))
    )

    assert ds.minLevelCell.values.tolist() == [1, 7]
    ref = ds.RefPseudoThickness
    np.testing.assert_allclose(ref.sum('nVertLevels'), [1000.0, 1000.0])
    np.testing.assert_allclose(
        ref.isel(nCells=1, nVertLevels=6) / ref.isel(nCells=1, nVertLevels=7),
        0.75,
    )


def _config(top_level='front_draft', percentile=20.0, max_rx1=30.0):
    config = PolarisConfigParser()
    config.add_section('vertical_grid')
    options = {
        'grid_type': 'uniform',
        'vert_levels': '10',
        'bottom_depth': '1000.0',
        'coord_type': 'z-star',
        'min_vert_levels': '3',
        'min_layer_thickness': '0.0',
        'partial_cell_type': 'none',
        'min_pc_fraction': '0.1',
        'ice_shelf_top_level': top_level,
        'ice_shelf_front_percentile': str(percentile),
        'ice_shelf_min_top_fraction': '0.5',
        'ice_shelf_max_rx1': str(max_rx1),
    }
    for option, value in options.items():
        config.set('vertical_grid', option, value)
    return config


def _strip(drafts, bed=None, dv_edge=None):
    """
    A strip of cells, each the next's neighbor, under land ice where the
    draft is positive
    """
    ncells = len(drafts)
    if bed is None:
        bed = [1000.0] * ncells
    if dv_edge is None:
        dv_edge = [1e3] * (ncells - 1)
    cells_on_edge = np.array([[i + 1, i + 2] for i in range(ncells - 1)])
    ds_mesh = xr.Dataset(
        {
            'cellsOnEdge': (('nEdges', 'TWO'), cells_on_edge),
            'dvEdge': (('nEdges',), np.array(dv_edge, dtype=float)),
        }
    )
    drafts = np.array(drafts, dtype=float)
    ssh = xr.DataArray(-drafts, dims=('nCells',))
    bottom = xr.DataArray(np.array(bed, dtype=float), dims=('nCells',))
    land_ice = xr.DataArray((drafts > 0).astype(int), dims=('nCells',))
    film = xr.zeros_like(land_ice)
    return ds_mesh, ssh, bottom, land_ice, film


def _max_rx1(config, ssh, bottom, top_depth, edges):
    """
    The largest rx1 over the given edges of the z-star columns starting at
    the given top depths
    """
    ds = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    init_vertical_coord(
        config, ds, top_depth=xr.DataArray(top_depth, dims=('nCells',))
    )
    z = ds.GeomZInterface.isel(Time=0).values
    h = ds.layerThickness.isel(Time=0).values
    kmin = ds.minLevelCell.values - 1
    kmax = ds.maxLevelCell.values - 1
    rx1 = 0.0
    for a, b in edges:
        for k in range(max(kmin[a], kmin[b]), min(kmax[a], kmax[b]) + 1):
            num = abs(z[a, k] - z[b, k] + z[a, k + 1] - z[b, k + 1])
            rx1 = max(rx1, num / (h[a, k] + h[b, k]))
    return rx1
