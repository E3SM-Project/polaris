"""
The times of the records in MALI's data-mode files

MALI's data mode steps from record to record without interpolating, so the
protocol's yearly geometry is interpolated to the start of each month, in
E3SM's no-leap calendar.
"""

import numpy as np

#: The seconds in a day
SECONDS_PER_DAY = 86400.0

#: The days in a year of E3SM's no-leap calendar
DAYS_PER_YEAR = 365

#: The day of the year on which each month of the no-leap calendar starts
MONTH_START_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def get_monthly_record_times(year_count):
    """
    Get the times of the records at the start of each month of years 1 to
    ``year_count``, and at the start of the year after

    Parameters
    ----------
    year_count : int
        The number of years the records span

    Returns
    -------
    xtimes : list of str
        MALI's ``xtime`` of each record, ``YYYY-MM-DD_hh:mm:ss``

    seconds : numpy.ndarray
        The time of each record in s since the start of year 1
    """
    xtimes = []
    days = []
    for year in range(1, year_count + 1):
        for month, start_day in enumerate(MONTH_START_DAYS):
            xtimes.append(f'{year:04d}-{month + 1:02d}-01_00:00:00')
            days.append((year - 1) * DAYS_PER_YEAR + start_day)
    xtimes.append(f'{year_count + 1:04d}-01-01_00:00:00')
    days.append(year_count * DAYS_PER_YEAR)
    seconds = SECONDS_PER_DAY * np.array(days, dtype=float)
    return xtimes, seconds


def get_interpolation_weights(times, record_times):
    """
    Get the records before and after each time and the weights for linear
    interpolation between them

    Parameters
    ----------
    times : numpy.ndarray
        The times to interpolate to

    record_times : numpy.ndarray
        The increasing times of the records

    Returns
    -------
    before : numpy.ndarray
        The index of the record at or before each time

    after : numpy.ndarray
        The index of the record after ``before``

    weight : numpy.ndarray
        The weight of the record ``after``, between 0 and 1

    Raises
    ------
    ValueError
        If a time is outside the records
    """
    times = np.asarray(times, dtype=float)
    record_times = np.asarray(record_times, dtype=float)
    if np.any(times < record_times[0]) or np.any(times > record_times[-1]):
        raise ValueError('Times must be within the times of the records.')
    before = np.searchsorted(record_times, times, side='right') - 1
    before = np.clip(before, 0, len(record_times) - 2)
    after = before + 1
    weight = (times - record_times[before]) / (
        record_times[after] - record_times[before]
    )
    return before, after, weight
