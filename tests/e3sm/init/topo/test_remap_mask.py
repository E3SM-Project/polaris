import configparser

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.remap.mask import MaskTopoStep


def test_ocean_masks_follow_antarctic_boundary_conventions():
    ds_topo = xr.Dataset(
        data_vars=dict(
            base_elevation=(
                'nCells',
                np.asarray([-100.0, -200.0, -300.0, 100.0, 50.0]),
            ),
            ice_mask=('nCells', np.asarray([0.0, 1.0, 1.0, 0.0, 1.0])),
            grounded_mask=(
                'nCells',
                np.asarray([0.0, 0.0, 1.0, 0.0, 1.0]),
            ),
        )
    )

    expected = {
        'calving_front': [1.0, 0.0, 0.0, 0.0, 0.0],
        'grounding_line': [1.0, 1.0, 0.0, 0.0, 0.0],
        'bedrock_zero': [1.0, 1.0, 1.0, 0.0, 0.0],
    }

    for convention, expected_ocean in expected.items():
        ocean_mask = MaskTopoStep._get_ocean_mask(
            base_elevation=ds_topo.base_elevation,
            ice_mask=ds_topo.ice_mask,
            grounded_mask=ds_topo.grounded_mask,
            convention=convention,
        )

        np.testing.assert_array_equal(ocean_mask.values, expected_ocean)


def test_missing_antarctic_boundary_convention_raises():
    config = configparser.ConfigParser()
    config.add_section('spherical_mesh')

    with pytest.raises(ValueError, match='Missing .*antarctic_boundary'):
        MaskTopoStep._get_antarctic_boundary_convention(config)
