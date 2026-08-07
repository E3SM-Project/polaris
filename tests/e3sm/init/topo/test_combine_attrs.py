"""
Unit tests for the metadata on combined topography fields.

The combine step is cached, so a mislabelled field here is expensive to fix:
it takes a full regeneration and re-upload of the combined topography.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.combine.step import _label_combined_fields

# Attributes the combined fields really used to inherit: latitude's, from the
# blending weight ``alpha``, and Bedmap3's surface-type flags, from the mask
# the ice fractions are derived from.
INHERITED = {
    'axis': 'Y',
    'valid_min': -90.0,
    'valid_max': 90.0,
    'bounds': 'lat_bnds',
    'standard_name': 'latitude',
    'long_name': 'Ice mask',
    'sdn_uom_name': 'Metres',
    'flag_values': np.array([1, 2, 3, 4]),
    'flag_meanings': 'grounded_ice floating_ice_shelf rock',
    'grid_mapping': 'mapping',
    'unit': 'meters',
}

FRACTIONS = ['ice_mask', 'grounded_mask', 'ocean_mask']
HEIGHTS = ['base_elevation', 'ice_draft', 'ice_thickness']


def _make_combined():
    """A combined dataset whose fields all carry the inherited attributes."""
    combined = xr.Dataset()
    for field in FRACTIONS + HEIGHTS:
        combined[field] = xr.DataArray(
            np.zeros((2, 2)), dims=['lat', 'lon'], attrs=dict(INHERITED)
        )
    return combined


def test_combined_fields_keep_none_of_the_inherited_attrs():
    combined = _make_combined()

    _label_combined_fields(combined)

    for field in FRACTIONS + HEIGHTS:
        attrs = combined[field].attrs
        assert set(attrs) == {'long_name', 'units'}, field


@pytest.mark.parametrize('field', FRACTIONS)
def test_fractions_are_dimensionless(field):
    """A fraction in [0, 1] is not a length, and is not a flag variable."""
    combined = _make_combined()

    _label_combined_fields(combined)

    assert combined[field].attrs['units'] == '1'
    assert 'fraction' in combined[field].attrs['long_name']


@pytest.mark.parametrize('field', HEIGHTS)
def test_heights_are_in_metres(field):
    combined = _make_combined()

    _label_combined_fields(combined)

    assert combined[field].attrs['units'] == 'm'


def test_each_field_gets_its_own_long_name():
    """grounded_mask used to call itself an ice mask."""
    combined = _make_combined()

    _label_combined_fields(combined)

    long_names = [combined[f].attrs['long_name'] for f in FRACTIONS + HEIGHTS]
    assert len(set(long_names)) == len(long_names)
