import cftime
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.model.time import get_days_since_start

# days since the reference date below that the test datasets sample
DAYS = np.array([0.0, 1.5, 10.25])

REFERENCE = '0001-01-01 00:00:00'

CALENDAR = 'noleap'

# seconds, hours and days per day, for building the units under test
PER_DAY = {'seconds': 86400.0, 'hours': 24.0, 'days': 1.0}


def _make_dataset(units='seconds', omega_attrs=False, with_units=True):
    """
    An Omega-like dataset with a decoded ``Time`` coordinate.  Times are
    cftime dates, so ``units`` belongs in ``encoding`` as xarray would
    leave it after decoding; ``Units`` is Omega's capitalized duplicate.
    """
    dates = cftime.num2date(
        DAYS * PER_DAY[units],
        units=f'{units} since {REFERENCE}',
        calendar=CALENDAR,
    )
    time = xr.DataArray(dates, dims=('Time',), name='Time')
    if with_units:
        time.encoding['units'] = f'{units} since {REFERENCE}'
    time.encoding['calendar'] = CALENDAR
    if omega_attrs:
        time.attrs['Units'] = f'{units} since {REFERENCE}'
    ds = xr.Dataset(coords={'Time': time})
    ds['SomeField'] = xr.DataArray(np.zeros(len(DAYS)), dims=('Time',))
    return ds


def _round_trip(ds, tmp_path):
    """Write with xarray and read back, as any test that generates its own
    input would."""
    path = tmp_path / 'output.nc'
    ds.to_netcdf(path)
    return xr.open_dataset(path)


def test_xarray_round_trip(tmp_path):
    """A file xarray wrote has 'units' in encoding and no 'Units' at all.
    This is the case that failed before the CF units were used."""
    ds = _round_trip(_make_dataset(), tmp_path)
    assert 'Units' not in ds['Time'].attrs
    assert 'units' not in ds['Time'].attrs
    assert ds['Time'].encoding['units'].startswith('seconds since')
    assert_allclose(get_days_since_start(ds), DAYS)


@pytest.mark.parametrize('units', ['seconds', 'hours', 'days'])
def test_omega_style_file(units, tmp_path):
    """An Omega file carries both 'Units' and the CF 'units'; the answer is
    unchanged from what the capitalized attribute gave for the 'seconds'
    that Omega writes, and is now right for other reference units too."""
    ds = _round_trip(_make_dataset(units=units, omega_attrs=True), tmp_path)
    assert ds['Time'].attrs['Units'] == f'{units} since {REFERENCE}'
    assert_allclose(get_days_since_start(ds), DAYS)


def test_undecoded_units_in_attrs():
    """A dataset that has not been through decoding still has its CF units
    in attrs."""
    ds = _make_dataset()
    units = ds['Time'].encoding.pop('units')
    ds['Time'].attrs['units'] = units
    assert_allclose(get_days_since_start(ds), DAYS)


@pytest.mark.parametrize('units', ['seconds', 'hours', 'days'])
def test_reference_units(units, tmp_path):
    """The reference units are not assumed to be seconds."""
    ds = _round_trip(_make_dataset(units=units), tmp_path)
    assert_allclose(get_days_since_start(ds), DAYS)


def test_missing_units_raises():
    """A time variable with no CF units at all is named in the error."""
    ds = _make_dataset(with_units=False)
    with pytest.raises(ValueError, match="'units' for time variable 'Time'"):
        get_days_since_start(ds)


def test_malformed_units_raises():
    """Units that are not '<units> since <reference>' are named too."""
    ds = _make_dataset()
    ds['Time'].encoding['units'] = 'seconds'
    with pytest.raises(ValueError, match="time variable 'Time'"):
        get_days_since_start(ds)


def test_no_time_variable():
    """The existing error for a dataset with no time variable is kept."""
    ds = xr.Dataset({'SomeField': xr.DataArray(np.zeros(3), dims=('x',))})
    with pytest.raises(ValueError, match='Could not find a time variable'):
        get_days_since_start(ds)
