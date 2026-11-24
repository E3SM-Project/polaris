import numpy as np
import xarray as xr
from numpy.testing import assert_array_equal

from polaris.tasks.ocean.isomip_plus.topo.calving import calve_thin_ice


def _make_geometry():
    """Five points: thick floating ice, thin floating ice, thin grounded
    ice, open ocean and thin ice that is only partly floating"""
    upper = np.array([100.0, 8.0, 50.0, 0.0, 5.0])
    lower = np.array([-700.0, -70.0, -30.0, 0.0, -40.0])
    floating = np.array([1.0, 1.0, 0.0, 0.0, 0.05])
    grounded = np.array([0.0, 0.0, 1.0, 0.0, 0.95])
    open_ocean = np.array([0.0, 0.0, 0.0, 1.0, 0.0])
    ds = xr.Dataset()
    for name, values in [
        ('upperSurface', upper),
        ('lowerSurface', lower),
        ('floatingMask', floating),
        ('groundedMask', grounded),
        ('openOceanMask', open_ocean),
    ]:
        ds[name] = ('x', values)
        ds[name].attrs['units'] = 'm' if 'Surface' in name else '1'
    return ds


def test_calve_thin_floating_ice():
    ds = _make_geometry()
    ds_calved = calve_thin_ice(ds, min_ice_thickness=100.0)

    # only the thin, floating ice (index 1) is calved
    assert_array_equal(
        ds_calved.upperSurface.values, [100.0, 0.0, 50.0, 0.0, 5.0]
    )
    assert_array_equal(
        ds_calved.lowerSurface.values, [-700.0, 0.0, -30.0, 0.0, -40.0]
    )
    assert_array_equal(
        ds_calved.floatingMask.values, [1.0, 0.0, 0.0, 0.0, 0.05]
    )
    assert_array_equal(
        ds_calved.openOceanMask.values, [0.0, 1.0, 0.0, 1.0, 0.0]
    )
    assert_array_equal(ds_calved.groundedMask.values, ds.groundedMask.values)


def test_calving_keeps_masks_summing_to_one():
    ds = _make_geometry()
    ds_calved = calve_thin_ice(ds, min_ice_thickness=100.0)
    total = (
        ds_calved.floatingMask
        + ds_calved.groundedMask
        + ds_calved.openOceanMask
    )
    assert np.allclose(total.values, 1.0)


def test_calving_does_not_modify_input_and_keeps_attrs():
    ds = _make_geometry()
    original = ds.copy(deep=True)
    ds_calved = calve_thin_ice(ds, min_ice_thickness=100.0)
    xr.testing.assert_identical(ds, original)
    assert ds_calved.lowerSurface.attrs == ds.lowerSurface.attrs


def test_calving_applies_to_each_time_record():
    ds = _make_geometry()
    ds = xr.concat([ds, ds], dim='t')
    ds['upperSurface'][1, 0] = 10.0
    ds['lowerSurface'][1, 0] = -80.0
    ds_calved = calve_thin_ice(ds, min_ice_thickness=100.0)
    assert ds_calved.floatingMask.values[0, 0] == 1.0
    assert ds_calved.floatingMask.values[1, 0] == 0.0
    assert ds_calved.openOceanMask.values[1, 0] == 1.0
