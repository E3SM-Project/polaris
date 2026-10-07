"""
Unit tests for the metadata of the fields
:py:func:`polaris.ocean.vertical.init_vertical_coord` creates.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical import init_vertical_coord

# what an init step's bottomDepth and ssh carried when made with
# ``xr.ones_like(ds.xCell)`` from a mesh
X_CELL_ATTRS = {'long_name': 'x-coordinates of cell centres', 'units': 'm'}

# every field init_vertical_coord creates from bottomDepth and ssh
DERIVED_VARS = [
    'minLevelCell',
    'maxLevelCell',
    'cellMask',
    'layerThickness',
    'restingThickness',
    'vertCoordMovementWeights',
    'zMid',
    'GeomZInterface',
]


def _make_config(coord_type):
    config = PolarisConfigParser()
    config.add_section('vertical_grid')
    options = {
        'coord_type': coord_type,
        'grid_type': 'uniform',
        'vert_levels': '4',
        'bottom_depth': '600.0',
        'min_vert_levels': '1',
        'min_layer_thickness': '0.0',
        'partial_cell_type': 'none',
        'min_pc_fraction': '0.1',
    }
    for option, value in options.items():
        config.set('vertical_grid', option, value)
    return config


def _make_ds():
    """A two-column dataset whose inputs carry a mesh coordinate's attrs."""
    ds = xr.Dataset()
    ds['bottomDepth'] = xr.DataArray(
        np.array([600.0, 300.0]), dims=['nCells'], attrs=X_CELL_ATTRS
    )
    ds['ssh'] = xr.DataArray(np.zeros(2), dims=['nCells'], attrs=X_CELL_ATTRS)
    return ds


@pytest.mark.parametrize('coord_type', ['z-level', 'z-star', 'sigma'])
def test_derived_fields_do_not_inherit_input_attrs(coord_type):
    """Nothing computed from bottomDepth and ssh claims to be xCell."""
    ds = _make_ds()

    init_vertical_coord(_make_config(coord_type), ds)

    for var in DERIVED_VARS:
        assert ds[var].attrs == {}, var
