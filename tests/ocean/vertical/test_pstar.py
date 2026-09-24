"""
Unit tests for
:py:func:`polaris.ocean.vertical.pstar.init_pstar_vertical_coord`.

These cover the metadata the function writes.  The numerical behaviour of the
coordinate is exercised through ``PStarInitStep`` in ``test_pstar_init.py``.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.pstar import init_pstar_vertical_coord

# Attributes a BottomPressure arriving from the topography chain really does
# carry.  ``unit`` (singular) and ``cell_measures`` come from the combined
# topography; ``long_name`` and ``units`` are set by the caller.
BAD_ATTRS = {
    'long_name': 'seafloor pressure',
    'units': 'Pa',
    'unit': 'meters',
    'cell_measures': 'area: area',
}

# every field init_pstar_vertical_coord creates
DERIVED_VARS = [
    'minLevelCell',
    'maxLevelCell',
    'cellMask',
    'RefPseudoThickness',
    'PseudoThickness',
    'ZTildeMid',
    'ZTildeInterface',
    'vertCoordMovementWeights',
]


def _make_config(partial_cell_type):
    config = PolarisConfigParser()
    config.add_section('vertical_grid')
    options = {
        'grid_type': 'uniform',
        'vert_levels': '4',
        'bottom_depth': '600.0',
        'min_vert_levels': '1',
        'min_layer_thickness': '0.0',
        'partial_cell_type': partial_cell_type,
        'min_pc_fraction': '0.1',
    }
    for option, value in options.items():
        config.set('vertical_grid', option, value)
    return config


def _make_ds(bottom_pressure_attrs):
    """A two-column dataset with the seeded BottomPressure attributes."""
    ncells = 2
    nvertlevels = 4
    ds = xr.Dataset(
        {
            'dummy': xr.DataArray(
                np.zeros((ncells, nvertlevels)),
                dims=['nCells', 'nVertLevels'],
            )
        }
    )
    bottom_pressure = xr.DataArray(
        np.array([5.0e6, 1.0e6]), dims=['nCells'], attrs=bottom_pressure_attrs
    )
    ds['BottomPressure'] = bottom_pressure
    ds['SurfacePressure'] = xr.DataArray(
        np.zeros(ncells), dims=['nCells'], attrs={}
    )
    return ds


@pytest.mark.parametrize('partial_cell_type', ['none', 'partial', 'full'])
def test_derived_fields_do_not_inherit_bottom_pressure_attrs(
    partial_cell_type,
):
    """No p-star field claims to be the pressure it was derived from.

    Seeding the input with attributes that must not survive is the point:
    xarray propagates them through the arithmetic, comparisons, ``where()``
    and ``zeros_like()`` calls this function uses, so the test fails in either
    direction if attribute handling changes.

    All three ``partial_cell_type`` settings are covered because they take
    different paths: ``partial`` and ``full`` rebuild the pseudo-depth from
    attribute-free arrays and so used to lose the labels by accident, while
    ``none`` carried them onto every field.
    """
    ds = _make_ds(BAD_ATTRS)

    init_pstar_vertical_coord(_make_config(partial_cell_type), ds)

    for var in DERIVED_VARS:
        attrs = ds[var].attrs
        assert attrs.get('units') != 'Pa', f'{var} claims to be in Pascals'
        assert 'unit' not in attrs, f'{var} inherited unit'
        assert 'cell_measures' not in attrs, f'{var} inherited cell_measures'
        assert attrs.get('long_name') != BAD_ATTRS['long_name'], (
            f'{var} claims to be a seafloor pressure'
        )


@pytest.mark.parametrize('partial_cell_type', ['none', 'partial', 'full'])
def test_derived_fields_are_all_labelled(partial_cell_type):
    """Every field the function creates says what it is.

    ``RefPseudoThickness`` and ``vertCoordMovementWeights`` used to come out
    with no attributes at all.
    """
    ds = _make_ds({})

    init_pstar_vertical_coord(_make_config(partial_cell_type), ds)

    for var in DERIVED_VARS:
        assert ds[var].attrs.get('long_name'), f'{var} has no long_name'

    # A one-based level index has no meaningful unit; everything else does.
    unitless = ['minLevelCell', 'maxLevelCell', 'cellMask']
    for var in DERIVED_VARS:
        has_units = 'units' in ds[var].attrs
        assert has_units == (var not in unitless), f'{var} units attribute'


@pytest.mark.parametrize('partial_cell_type', ['none', 'partial', 'full'])
def test_bottom_pressure_keeps_the_callers_attrs(partial_cell_type):
    """The post-snap overwrite does not strip BottomPressure's metadata.

    The caller owns that variable — ``horiz_press_grad`` calls it a seafloor
    *gauge* pressure — so whatever it was given survives.
    """
    attrs = {'long_name': 'seafloor gauge pressure', 'units': 'Pa'}
    ds = _make_ds(attrs)

    init_pstar_vertical_coord(_make_config(partial_cell_type), ds)

    assert ds.BottomPressure.attrs == attrs
