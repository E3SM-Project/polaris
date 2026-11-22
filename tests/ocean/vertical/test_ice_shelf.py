"""
Unit tests for :py:mod:`polaris.ocean.vertical.ice_shelf` and for z-star and
p-star columns that start below the top reference level.

The reference grid in these tests has 10 levels of 100 m, so a draft of 250 m
lies below 2 whole levels and one of 650 m below 6.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.ice_shelf import (
    compute_ice_shelf_groups,
    compute_ice_shelf_min_level_cell,
    weighted_percentile,
)
from polaris.ocean.vertical.pstar import init_pstar_vertical_coord

GRAVITY = get_constant('standard_acceleration_of_gravity')
RHO_SW = get_constant('seawater_density_reference')
FILM = 0.05


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


def test_surface_keeps_every_column_at_the_top_level():
    ds_mesh, ssh, bottom, land_ice, film = _strip([0, 250, 450, 650])
    config = _config(top_level='surface')

    min_level_cell, group = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert min_level_cell.values.tolist() == [0, 0, 0, 0]
    assert group.values.tolist() == [0, 1, 1, 1]


@pytest.mark.parametrize('percentile, inner_drop', [(20.0, 2), (50.0, 6)])
def test_front_cells_take_their_own_draft(percentile, inner_drop):
    """
    Front cells 1 (draft 250 m, front 1 km long) and 4 (650 m, 4 km) take the
    levels above their own drafts.  The inner cells take the percentile of
    the front drafts weighted by front length.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 550, 650, 0], dv_edge=[1e3, 1e3, 1e3, 1e3, 4e3]
    )
    config = _config(percentile=percentile, max_rx1=np.inf)

    min_level_cell, _ = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert min_level_cell.values.tolist() == [
        0,
        2,
        inner_drop,
        inner_drop,
        6,
        0,
    ]


def test_ice_facing_a_shallower_bed_is_not_a_front():
    """
    Cell 1 meets open water whose bed (200 m) is above its draft, so only
    cell 2 is a front, and cell 1 takes the shelf's drop from it.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 0], bed=[200, 1000, 1000, 1000]
    )
    config = _config(max_rx1=np.inf)

    min_level_cell, _ = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert min_level_cell.values.tolist() == [0, 4, 4, 0]


def test_ice_below_a_neighbors_seafloor_shares_no_levels_with_it():
    """
    Cell 1's water, under a 650 m draft, lies entirely below the 450 m bed
    of open-water cell 0 (levels 0-4), so it starts below them.  Cell 0's
    bed is above the draft, so the edge is not a front.
    """
    ds_mesh, ssh, bottom, land_ice, film = _strip([0, 650], bed=[450, 1000])
    config = _config(max_rx1=np.inf)

    min_level_cell, _ = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert min_level_cell.values.tolist() == [0, 5]


def test_film_cells_drop_nothing():
    ds_mesh, ssh, bottom, land_ice, film = _strip(
        [0, 250, 450, 1000 - 3 * FILM]
    )
    film[3] = 1
    config = _config(max_rx1=np.inf)

    min_level_cell, group = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )

    assert min_level_cell.values.tolist() == [0, 2, 2, 0]
    assert group.values.tolist() == [0, 1, 1, 1]


def test_a_steep_edge_gets_the_fewest_extra_drops():
    """
    Behind a front at 250 m, the shelf drops 2 levels.  At each steep edge,
    the deeper cell then drops just enough more to bring rx1 to the maximum,
    with its neighbor at the shelf's drop.
    """
    drafts = [0, 250, 450, 650]
    ds_mesh, ssh, bottom, land_ice, film = _strip(drafts)
    config = _config(max_rx1=1.0)

    min_level_cell, _ = compute_ice_shelf_min_level_cell(
        config, ds_mesh, ssh, bottom, land_ice, film, FILM
    )
    ndrop = min_level_cell.values

    base = np.array([0, 2, 2, 2])
    assert ndrop[1] == 2
    for cell, edge in [(2, (1, 2)), (3, (2, 3))]:
        assert ndrop[cell] > base[cell]
        drops = base.copy()
        drops[cell] = ndrop[cell]
        assert _max_rx1(config, ssh, bottom, drops, [edge]) <= 1.0
        drops[cell] -= 1
        assert _max_rx1(config, ssh, bottom, drops, [edge]) > 1.0


def test_z_star_with_dropped_levels_sums_to_the_bed():
    ds_mesh, ssh, bottom, land_ice, film = _strip([0, 250, 650])
    config = _config()
    ds = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    min_level_cell = xr.DataArray([0, 2, 9], dims=('nCells',))

    init_vertical_coord(config, ds, min_level_cell=min_level_cell)

    # 9 is capped to keep 3 levels
    assert ds.minLevelCell.values.tolist() == [1, 3, 8]
    resting = ds.restingThickness.isel(Time=0).sum('nVertLevels')
    np.testing.assert_allclose(resting.values, bottom.values)
    thickness = ds.layerThickness.isel(Time=0).sum('nVertLevels')
    np.testing.assert_allclose(thickness.values, (ssh + bottom).values)


def test_z_star_without_dropped_levels_is_unchanged():
    ds_mesh, ssh, bottom, land_ice, film = _strip([0, 250, 650])
    config = _config()
    ds_default = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    ds_zero = ds_default.copy()

    init_vertical_coord(config, ds_default)
    init_vertical_coord(
        config, ds_zero, min_level_cell=xr.zeros_like(bottom).astype(int)
    )

    xr.testing.assert_identical(ds_default, ds_zero)


def test_p_star_with_dropped_levels_sums_to_the_bed():
    config = _config()
    ds = xr.Dataset(
        {
            'BottomPressure': xr.DataArray(
                RHO_SW * GRAVITY * np.array([1000.0, 1000.0]),
                dims=('nCells',),
            ),
            'SurfacePressure': xr.DataArray(
                RHO_SW * GRAVITY * np.array([0.0, 650.0]), dims=('nCells',)
            ),
        }
    )

    init_pstar_vertical_coord(
        config, ds, min_level_cell=xr.DataArray([0, 6], dims=('nCells',))
    )

    assert ds.minLevelCell.values.tolist() == [1, 7]
    total = ds.RefPseudoThickness.sum('nVertLevels')
    np.testing.assert_allclose(total.values, [1000.0, 1000.0])


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


def _max_rx1(config, ssh, bottom, ndrop, edges):
    """
    The largest rx1 over the given edges of the z-star columns with the
    given drops
    """
    ds = xr.Dataset({'ssh': ssh, 'bottomDepth': bottom})
    init_vertical_coord(
        config, ds, min_level_cell=xr.DataArray(ndrop, dims=('nCells',))
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
