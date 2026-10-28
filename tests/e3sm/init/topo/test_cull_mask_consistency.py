import logging

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.cull.consistency import (
    check_critical_passages,
    check_cull_mask_consistency,
    check_land_locked_criteria,
    check_sea_ice_removed_regions,
)
from tests.mesh.hex_mesh import cell_index, hex_mesh

# four base-mesh cells: 0 and 1 are ocean, 2 and 3 are land and land ice
OCEAN = [0, 0, 1, 1]
NO_CAVITIES = [0, 0, 1, 1]
LAND = [1, 1, 0, 0]
LAND_ICE = [0, 0, 1, 1]


@pytest.mark.parametrize(
    'convention', ['calving_front', 'grounding_line', 'bedrock_zero']
)
def test_consistent_masks_pass(convention):
    _check(convention=convention)


def test_no_cavities_not_a_subset_of_ocean_fails():
    # cell 1 is kept without cavities but culled from the ocean
    with pytest.raises(ValueError, match='but not in the ocean'):
        _check(
            ocean=[0, 1, 1, 1],
            no_cavities=[0, 0, 1, 1],
            land=[1, 1, 0, 0],
            land_ice=[0, 0, 1, 1],
        )


def test_land_not_the_complement_of_no_cavities_fails():
    # cell 1 is owned by both the ocean without cavities and the land
    with pytest.raises(ValueError, match='not the complement'):
        _check(land=[1, 0, 0, 0])


def test_land_ice_inside_no_cavities_fails():
    # cell 1 is flagged as land ice but retained without cavities
    with pytest.raises(ValueError, match='flagged as land ice'):
        _check(land_ice=[0, 1, 1, 1])


def test_cavity_is_allowed_with_cavity_conventions():
    # cell 1 is an ice-shelf cavity: in the ocean, out of the ocean
    # without cavities, owned by the land, flagged as land ice
    for convention in ['grounding_line', 'bedrock_zero']:
        _check(
            convention=convention,
            ocean=[0, 0, 1, 1],
            no_cavities=[0, 1, 1, 1],
            land=[1, 0, 0, 0],
            land_ice=[0, 1, 1, 1],
        )


def test_cavity_is_rejected_with_calving_front():
    with pytest.raises(ValueError, match='no ice-shelf cavities'):
        _check(
            convention='calving_front',
            ocean=[0, 0, 1, 1],
            no_cavities=[0, 1, 1, 1],
            land=[1, 0, 0, 0],
            land_ice=[0, 1, 1, 1],
        )


def test_offending_cells_are_listed():
    with pytest.raises(ValueError, match=r'flagged as land ice.*: 0, 1'):
        _check(land_ice=[1, 1, 1, 1])


def test_offending_cells_are_truncated():
    n_cells = 40
    zeros = [0] * n_cells
    with pytest.raises(ValueError, match=r'\.\.\.'):
        _check(
            ocean=zeros,
            no_cavities=zeros,
            land=[1] * n_cells,
            land_ice=[1] * n_cells,
        )


def _check(
    convention='calving_front',
    ocean=OCEAN,
    no_cavities=NO_CAVITIES,
    land=LAND,
    land_ice=LAND_ICE,
):
    check_cull_mask_consistency(
        ocean_cull_mask=np.asarray(ocean),
        ocean_no_cavities_cull_mask=np.asarray(no_cavities),
        land_cull_mask=np.asarray(land),
        land_ice_mask=np.asarray(land_ice),
        convention=convention,
        logger=logging.getLogger('test_cull_mask_consistency'),
    )


def test_domains_differing_by_a_non_cavity_fails():
    # cell 1 is in the ocean but not without cavities, and is not land ice
    with pytest.raises(ValueError, match='differ by something other'):
        _check(
            convention='grounding_line',
            ocean=[0, 0, 1, 1],
            no_cavities=[0, 1, 1, 1],
            land=[1, 0, 0, 0],
            land_ice=[0, 0, 1, 1],
        )


def test_land_ice_in_the_ocean_fails_under_calving_front():
    with pytest.raises(ValueError, match='leaves no ice-shelf cavities'):
        _check(land_ice=[1, 0, 1, 1])


def test_land_locked_criteria_pass_on_a_clean_domain():
    ds_mesh = hex_mesh(5, 5, lat_of_row=lambda row: 20.0)
    cull = _cull(_all_cells(5, 5))
    check_land_locked_criteria(
        ds_mesh=ds_mesh,
        ocean_cull_mask=cull,
        ocean_no_cavities_cull_mask=cull,
        latitude_threshold=43.0,
        logger=logging.getLogger('test_cull_mask_consistency'),
    )


def test_land_locked_criteria_catch_a_dead_end():
    ds_mesh = hex_mesh(5, 5, lat_of_row=lambda row: 20.0)
    keep = np.zeros(25, dtype=bool)
    keep[cell_index(5, 1, 1)] = True
    keep[ds_mesh.cellsOnCell.values[cell_index(5, 1, 1), 0] - 1] = True
    cull = _cull(keep)

    with pytest.raises(ValueError, match='fewer than two active edges'):
        check_land_locked_criteria(
            ds_mesh=ds_mesh,
            ocean_cull_mask=cull,
            ocean_no_cavities_cull_mask=cull,
            latitude_threshold=43.0,
            logger=logging.getLogger('test_cull_mask_consistency'),
        )


def test_land_locked_criteria_catch_a_missing_vertex_poleward():
    # a row of cells: two active edges each, but no active vertex
    ds_mesh = hex_mesh(5, 5, lat_of_row=lambda row: 60.0 if row else 20.0)
    keep = np.zeros(25, dtype=bool)
    for col in range(5):
        keep[cell_index(5, col, 0)] = True
        keep[cell_index(5, col, 2)] = True
    cull = _cull(keep)

    with pytest.raises(ValueError, match='no active vertex'):
        check_land_locked_criteria(
            ds_mesh=ds_mesh,
            ocean_cull_mask=cull,
            ocean_no_cavities_cull_mask=cull,
            latitude_threshold=43.0,
            logger=logging.getLogger('test_cull_mask_consistency'),
        )


def _all_cells(n_cols, n_rows):
    return np.ones(n_cols * n_rows, dtype=bool)


def _cull(keep_mask):
    return np.where(keep_mask, 0, 1)


def test_removing_a_small_pocket_passes():
    # a few small cells removed is a pocket, not a sea
    _check_removed(n_removed_rows=1, cell_area=1.0e3)


def test_removing_many_small_cells_passes():
    # many cells but a small area, like a fjord on a fine mesh
    _check_removed(n_removed_rows=3, cell_area=1.0e3)


def test_removing_a_few_large_cells_passes():
    # a large area but few cells, like a pocket on a coarse mesh
    _check_removed(n_removed_rows=1, cell_area=1.0e5)


def test_removing_a_sea_fails():
    with pytest.raises(ValueError, match=r'whole seas.*\n  15 cells'):
        _check_removed(n_removed_rows=3, cell_area=1.0e5)


def _check_removed(n_removed_rows, cell_area):
    """
    Remove the top rows of a 5x5 lattice of cells, each ``cell_area`` km^2,
    and check the result against limits of 10 cells and 1e5 km^2.
    """
    ds_mesh = hex_mesh(5, 5)
    ds_mesh['areaCell'] = ('nCells', np.full(25, cell_area * 1e6))
    preliminary = _cull(_all_cells(5, 5))
    final = preliminary.copy()
    for row in range(5 - n_removed_rows, 5):
        for col in range(5):
            final[cell_index(5, col, row)] = 1
    check_sea_ice_removed_regions(
        ds_mesh=ds_mesh,
        preliminary_ocean_cull_mask=preliminary,
        ocean_cull_mask=final,
        max_region_cells=10,
        max_region_area=1.0e5,
        logger=logging.getLogger('test_cull_mask_consistency'),
    )


def test_passage_losing_a_cell_fails():
    with pytest.raises(ValueError, match=r"1 cells culled .* 'Strait': 2"):
        _check_passage(culled=[0, 0, 1, 0])


def test_passage_losing_a_dead_end_passes():
    _check_passage(culled=[0, 0, 1, 0], dead_ends=[0, 0, 1, 0])


def test_passage_dead_ends_do_not_excuse_other_cells():
    with pytest.raises(ValueError, match=r"1 cells culled .* 'Strait': 1"):
        _check_passage(culled=[0, 1, 1, 0], dead_ends=[0, 0, 1, 0])


def _check_passage(culled, dead_ends=None):
    """
    Check a single passage along cells 1 and 2 of four cells.
    """
    ds_transects = xr.Dataset(
        data_vars=dict(
            transectCellMasks=(
                ('nCells', 'nTransects'),
                np.array([[0], [1], [1], [0]]),
            ),
            transectNames=('nTransects', ['Strait']),
        )
    )
    check_critical_passages(
        ocean_cull_mask=np.asarray(culled),
        ds_transects=ds_transects,
        logger=logging.getLogger('test_cull_mask_consistency'),
        dead_end_mask=None if dead_ends is None else np.asarray(dead_ends),
    )
