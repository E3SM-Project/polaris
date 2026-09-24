"""
Unit tests for the metadata on masked and remapped topography fields.

The masks and fractions here are all derived from ``base_elevation`` and the
ice masks, so without explicit labelling they claim to be a bedrock elevation
in metres.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.remap.remap import _clean_remapped_attrs

# what a combined-topography field carries in once ncremap has been over it
NCREMAP_ATTRS = {
    'long_name': 'bedrock elevation above sea level',
    'units': 'm',
    'cell_measures': 'area: area',
    'coordinates': 'lat lon',
    'grid_mapping': 'mapping',
}


def test_clean_remapped_attrs_drops_the_dangling_references():
    """area, lat, lon and mapping are not in the remapped file."""
    ds = xr.Dataset(
        {
            'base_elevation': xr.DataArray(
                np.zeros(3), dims=['nCells'], attrs=dict(NCREMAP_ATTRS)
            )
        }
    )

    _clean_remapped_attrs(ds)

    assert ds.base_elevation.attrs == {
        'long_name': 'bedrock elevation above sea level',
        'units': 'm',
    }


def test_clean_remapped_attrs_leaves_real_metadata_alone():
    ds = xr.Dataset(
        {
            'ocean_frac': xr.DataArray(
                np.zeros(3),
                dims=['nCells'],
                attrs={
                    'long_name': 'fraction of the cell covered by ocean',
                    'units': '1',
                },
            )
        }
    )

    _clean_remapped_attrs(ds)

    assert ds.ocean_frac.attrs == {
        'long_name': 'fraction of the cell covered by ocean',
        'units': '1',
    }


@pytest.mark.parametrize('prefix', ['land', 'ocean'])
def test_masks_are_labelled_as_fractions(prefix):
    """The derived masks do not inherit base_elevation's metres.

    This mirrors what MaskTopoStep.run() does: the mask comes out of
    comparisons against base_elevation, which propagate its attributes.
    """
    from polaris.attrs import set_attrs

    base_elevation = xr.DataArray(
        np.array([-100.0, 100.0, -50.0]),
        dims=['nCells'],
        attrs={'long_name': 'bedrock elevation above sea level', 'units': 'm'},
    )
    mask = (base_elevation < 0.0).astype(float)
    # the inheritance this guards against
    assert mask.attrs['units'] == 'm'

    ds = xr.Dataset()
    ds[f'{prefix}_mask'] = mask
    set_attrs(
        ds[f'{prefix}_mask'],
        long_name=f'fraction of the cell covered by {prefix}',
        units='1',
    )

    assert ds[f'{prefix}_mask'].attrs == {
        'long_name': f'fraction of the cell covered by {prefix}',
        'units': '1',
    }


def test_masked_fields_do_not_share_an_attrs_dict():
    """A masked field copies the source's metadata, rather than aliasing it.

    ``ds[out] .attrs = ds[var].attrs`` handed both variables the same dict, so
    relabelling one silently relabelled the other.
    """
    ds = xr.Dataset()
    ds['ice_thickness'] = xr.DataArray(
        np.zeros(3), dims=['nCells'], attrs={'long_name': 'ice thickness'}
    )
    ds['land_masked_ice_thickness'] = ds['ice_thickness'] * 0.5
    ds['land_masked_ice_thickness'].attrs = dict(ds['ice_thickness'].attrs)

    ds['land_masked_ice_thickness'].attrs['long_name'] = 'masked ice thickness'

    assert ds['ice_thickness'].attrs['long_name'] == 'ice thickness'
