import numpy as np
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.exchange import (
    SECONDS_PER_YEAR,
    compare_with_landice,
    read_landice_steps,
)


def _write_stats(path, ends, lengths, melt):
    """Write MALI's global statistics for steps ending at the given days of
    year 1, with the melt (kg s-1) applied in each"""
    xtime = [
        f'0001-01-{1 + int(day):02d}_{int(round(24 * (day % 1))):02d}:00:00'
        for day in ends
    ]
    ds = xr.Dataset()
    ds['xtime'] = ('Time', np.array(xtime, dtype='S64'))
    ds['deltat'] = ('Time', 86400.0 * np.array(lengths))
    ds['totalFloatingBasalMassBal'] = (
        'Time',
        -SECONDS_PER_YEAR * np.array(melt),
    )
    ds.to_netcdf(path)


def test_mali_s_steps_are_read_once_with_melt_positive(tmp_path):
    """A restart writes the step it starts from again; it counts once."""
    first = str(tmp_path / 'first.nc')
    second = str(tmp_path / 'second.nc')
    _write_stats(first, [0.0, 1.0, 2.0], [1.0, 1.0, 1.0], [0.0, 5.0, 6.0])
    _write_stats(second, [2.0, 2.5, 3.0], [1.0, 0.5, 0.5], [6.0, 7.0, 8.0])

    steps = read_landice_steps([first, second])

    np.testing.assert_allclose(steps.stepEnd, [0.0, 1.0, 2.0, 2.5, 3.0])
    np.testing.assert_allclose(steps.stepLength, [1.0, 1.0, 1.0, 0.5, 0.5])
    np.testing.assert_allclose(steps.appliedMelt, [0.0, 5.0, 6.0, 7.0, 8.0])


def _ocean_days(sent):
    """The ocean's daily flux sent, over days 0, 1, 2, ..."""
    count = len(sent)
    ds = xr.Dataset()
    ds['periodStart'] = ('Time', np.arange(count, dtype=float))
    ds['periodEnd'] = ('Time', np.arange(1, count + 1, dtype=float))
    ds['totalFluxSentToLandIce'] = ('Time', np.array(sent))
    return ds


def _steps(melt, lengths=None):
    """MALI's steps from day 0, each a day long unless given"""
    if lengths is None:
        lengths = np.ones(len(melt))
    steps = xr.Dataset()
    steps['stepEnd'] = ('nSteps', np.cumsum(lengths))
    steps['stepLength'] = ('nSteps', np.array(lengths, dtype=float))
    steps['appliedMelt'] = ('nSteps', np.array(melt, dtype=float))
    return steps


def test_mali_applies_each_day_s_melt_over_the_same_day():
    """MALI's step over day d applies the ocean's day-d melt, so the
    ocean's days match MALI's same days, and a shift of one interval
    compares each with MALI's next day, which the last day lacks."""
    ds_ocean = _ocean_days([10.0, 20.0, 30.0])
    steps = _steps([10.0, 20.0, 30.0 * 1.01])

    ds = compare_with_landice(ds_ocean, steps, interval=1.0, start=0.0)

    np.testing.assert_allclose(ds.landiceApplied, [10.0, 20.0, 30.3])
    np.testing.assert_allclose(ds.relativeDifference, [0.0, 0.0, 0.01])
    np.testing.assert_allclose(ds.landiceCoverage, [1.0, 1.0, 1.0])
    np.testing.assert_array_equal(ds.initialStart, [True, False, False])

    ds_shifted = compare_with_landice(
        ds_ocean, steps, interval=1.0, start=0.0, shift=1
    )
    np.testing.assert_allclose(ds_shifted.landiceApplied[:2], [20.0, 30.3])
    np.testing.assert_allclose(ds_shifted.landiceCoverage, [1.0, 1.0, 0.0])


def test_mali_s_melt_is_averaged_over_its_steps_in_a_period():
    """Steps shorter than the period are weighted by their length, and a
    period MALI has not reached is only partly covered."""
    ds_ocean = _ocean_days([12.0, 0.0])
    ds_ocean['periodEnd'] = ('Time', np.array([2.0, 4.0]))
    ds_ocean['periodStart'] = ('Time', np.array([0.0, 2.0]))
    # half-day steps from day 0 to day 4
    steps = _steps(
        [0.0, 0.0, 10.0, 10.0, 16.0, 16.0, 0.0, 0.0], lengths=0.5 * np.ones(8)
    )

    ds = compare_with_landice(
        ds_ocean, steps, interval=1.0, start=None, shift=1
    )

    # MALI's days 1 to 3: two half days at 10 and two at 16
    np.testing.assert_allclose(ds.landiceApplied[0], 13.0)
    # days 3 to 5, of which MALI reached only day 3 to 4
    np.testing.assert_allclose(ds.landiceCoverage, [1.0, 0.5])
    assert not bool(ds.initialStart.any())
