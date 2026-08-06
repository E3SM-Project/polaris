"""
Unit tests for :py:func:`polaris.attrs.set_attrs`.
"""

import numpy as np
import xarray as xr

from polaris.attrs import set_attrs


def _make_da():
    """A DataArray carrying metadata that a derived field must not keep."""
    return xr.DataArray(
        data=np.array([1.0e7, 2.0e7]),
        dims=['nCells'],
        attrs={
            'long_name': 'seafloor pressure',
            'units': 'Pa',
            'unit': 'meters',
            'cell_measures': 'area: area',
        },
    )


def test_existing_attrs_are_discarded():
    """Attributes not named in the call do not survive."""
    da = set_attrs(_make_da(), long_name='layer thickness', units='m')

    assert da.attrs == {'long_name': 'layer thickness', 'units': 'm'}


def test_omitted_attrs_are_absent():
    """``long_name`` and ``units`` are left out when not given.

    An absent ``units`` is the right answer for a one-based level index; an
    empty string or a made-up unit would not be.
    """
    da = set_attrs(_make_da(), long_name='Index to the last active cell.')

    assert da.attrs == {'long_name': 'Index to the last active cell.'}

    da = set_attrs(_make_da())

    assert da.attrs == {}


def test_extra_attrs_are_passed_through():
    da = set_attrs(
        _make_da(),
        long_name='sea gauge pressure',
        units='Pa',
        note='p = -RhoSw * g * z_tilde',
    )

    assert da.attrs == {
        'long_name': 'sea gauge pressure',
        'units': 'Pa',
        'note': 'p = -RhoSw * g * z_tilde',
    }


def test_returns_the_same_array_for_inline_use():
    da = _make_da()

    assert set_attrs(da, units='m') is da


def test_labels_a_variable_through_its_dataset():
    """``set_attrs(ds.var, ...)`` reaches the dataset.

    ``ds[var]`` returns a DataArray sharing the underlying ``Variable``, so
    the in-place assignment is visible through the dataset.
    """
    ds = xr.Dataset({'bottomDepth': _make_da()})

    set_attrs(ds.bottomDepth, long_name='seafloor geometric depth', units='m')

    assert ds.bottomDepth.attrs == {
        'long_name': 'seafloor geometric depth',
        'units': 'm',
    }


def test_labelling_one_dataset_variable_does_not_affect_another():
    """Two dataset variables built from one array are labelled separately.

    ``ds[name] = da`` copies the attributes, so ``layerThickness`` and
    ``restingThickness`` can share an array and still say different things.
    """
    da = _make_da()
    ds = xr.Dataset()
    ds['restingThickness'] = da
    set_attrs(ds.restingThickness, long_name='resting layer thickness')
    ds['layerThickness'] = da
    set_attrs(ds.layerThickness, long_name='layer thickness')

    assert ds.restingThickness.attrs['long_name'] == 'resting layer thickness'
    assert ds.layerThickness.attrs['long_name'] == 'layer thickness'
    assert da.attrs['long_name'] == 'seafloor pressure'


def test_xarray_still_propagates_attrs_to_derived_arrays():
    """The reason this helper exists, asserted rather than assumed.

    xarray keeps ``attrs`` through the operations Polaris uses to derive
    level indices and masks.  If a future xarray stops doing so, this test
    fails and the helper can be reconsidered; until then, every written
    variable needs its attributes set explicitly.
    """
    da = _make_da()

    for derived in [
        da / 2.0,
        da >= 0.0,
        xr.zeros_like(da),
        xr.ones_like(da),
        da.where(da > 0.0),
        xr.where(da > 0.0, da, 0.0),
        np.maximum(da, 0.0),
        np.logical_and(da > 0.0, da > 1.0),
    ]:
        assert derived.attrs == da.attrs
