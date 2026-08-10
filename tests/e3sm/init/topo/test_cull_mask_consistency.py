import logging

import numpy as np
import pytest

from polaris.tasks.e3sm.init.topo.cull.consistency import (
    check_cull_mask_consistency,
)

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
