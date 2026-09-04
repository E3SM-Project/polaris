import re
import time

import cftime
import numpy as np
import pandas as pd

from polaris.mpas.time import time_since_start


def get_days_since_start(ds):
    """
    Ocean model output may or may not include 'daysSinceStartOfSim'. This
    routine uses 'daysSinceStartOfSim' if available, otherwise it uses 'Time'
    """
    if 'daysSinceStartOfSim' in ds.keys():
        t_arr = ds.daysSinceStartOfSim.values.astype(float)
    elif 'xtime' in ds.keys():
        # Calculate seconds since the first timestamp
        seconds_since_start = time_since_start(ds.xtime.values)
        # Convert to days
        t_arr = np.array(seconds_since_start, dtype=float) / 86400.0
    elif 'Time' in ds.keys():
        # This option works if decode_times=True when loading xr.Dataset
        if 'Time' in ds['Time'].coords:
            t_arr = cftime.date2num(
                ds['Time'].values,
                units=_get_days_since_units(ds['Time']),
                calendar=ds['Time'].dt.calendar,
                has_year_zero=True,
            )
        else:
            t_pd = pd.to_datetime(ds['Time'].values)
            t_arr = 1.0e9 * (t_pd - t_pd[0]) / np.timedelta64(1, 's')
            t_arr = t_arr.astype(float) / 86400.0
    else:
        raise ValueError('Could not find a time variable in dataset')
    return t_arr


# the number of days in a year of each calendar cftime supports; the mixed
# Julian/Gregorian calendars use the mean Gregorian year, which is what a
# time axis in years wants
DAYS_PER_YEAR = {
    'noleap': 365.0,
    '365_day': 365.0,
    'all_leap': 366.0,
    '366_day': 366.0,
    '360_day': 360.0,
    'julian': 365.25,
    'standard': 365.2425,
    'gregorian': 365.2425,
    'proleptic_gregorian': 365.2425,
}


def days_per_year(calendar):
    """
    Get the length of a year in days in a given calendar

    Parameters
    ----------
    calendar : str
        The name of a CF calendar, as ``xarray.DataArray.dt.calendar`` gives
        it

    Returns
    -------
    days : float
        The number of days in a year of that calendar

    Raises
    ------
    ValueError
        If the calendar is not one of those CF defines
    """
    if calendar not in DAYS_PER_YEAR:
        known = ', '.join(DAYS_PER_YEAR)
        raise ValueError(
            f'Do not know the length of a year in the "{calendar}" '
            f'calendar.  The calendars supported are: {known}.'
        )
    return DAYS_PER_YEAR[calendar]


def get_simulation_years(ds, time_var='Time'):
    """
    Get the time axis of a dataset in decimal simulation years

    The year comes from the calendar date itself rather than from an elapsed
    time, so that a series covering years 21 through 40 is plotted at 21
    through 41 -- the years the user asked for -- whatever reference date the
    model happened to write its time coordinate against.  It also depends on
    no attribute of the time variable beyond its calendar, so a file that has
    been read and written again is handled the same as one straight from the
    model.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with a decoded time coordinate

    time_var : str, optional
        The name of the time coordinate

    Returns
    -------
    years : numpy.ndarray
        The decimal simulation year of each time in the dataset
    """
    times = ds[time_var]
    length = days_per_year(times.dt.calendar)
    seconds = (
        times.dt.hour * 3600 + times.dt.minute * 60 + times.dt.second
    ).values.astype(float)
    day_of_year = times.dt.dayofyear.values.astype(float)
    year = times.dt.year.values.astype(float)
    return year + (day_of_year - 1.0 + seconds / 86400.0) / length


def get_time_interval_string(days=None, seconds=None):
    """
    Convert a time interval in days and/or seconds to a string for use in a
    model config option.  If both are provided, they will be added

    Parameters
    ----------
    days : float, optional
        A time interval in days

    seconds : float, optional
        A time interval in seconds

    Returns
    -------
    time_str : str
        The time as a string in the format "DDDD_HH:MM:SS.SS"

    """
    sec_per_day = 86400
    total = 0.0
    if seconds is not None:
        total += seconds
    if days is not None:
        total += sec_per_day * days

    day_part = int(total / sec_per_day)
    sec_part = total - day_part * sec_per_day
    sec_decimal = sec_part - np.floor(sec_part)
    # https://stackoverflow.com/a/1384565/7728169
    seconds_str = time.strftime('%H:%M:%S', time.gmtime(sec_part))
    time_str = f'{day_part:04d}_{seconds_str}.{int(sec_decimal * 1e3):03d}'
    return time_str


def _get_days_since_units(da):
    """
    Get CF time units of the form ``days since <reference>`` for a time
    variable, taking the reference date from the CF ``units`` attribute
    whatever units it is expressed in.

    Parameters
    ----------
    da : xarray.DataArray
        A time variable.  When times have been decoded, xarray has moved
        ``units`` from ``attrs`` into ``encoding``, so both are checked.

    Returns
    -------
    units : str
        The CF units with the time unit replaced by ``days``
    """
    name = da.name if da.name is not None else 'time'
    if 'units' in da.encoding:
        units = da.encoding['units']
    elif 'units' in da.attrs:
        units = da.attrs['units']
    else:
        raise ValueError(
            f"Could not find CF 'units' for time variable '{name}' in "
            f'either its encoding or its attributes'
        )

    match = re.match(r'\s*\S+\s+since\s+(?P<reference>.+)', units)
    if match is None:
        raise ValueError(
            f"CF 'units' for time variable '{name}' are not of the form "
            f"'<units> since <reference>': '{units}'"
        )

    return f'days since {match.group("reference").strip()}'
