"""
Times in E3SM's 365-day calendar, which the MPAS components write as
``xtime`` strings
"""

import re

import numpy as np

#: The days in each month of the 365-day calendar
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

#: The label of a time axis in model years
MODEL_YEAR_LABEL = 'Model year'

#: MPAS writes years with 4 or more digits, such as ``00000-01-01_00:00:00``
_XTIME = re.compile(r'^\s*(-?\d+)-(\d{2})-(\d{2})_(\d{2}):(\d{2}):(\d{2})')


def xtime_to_days(xtime):
    """
    Convert MPAS ``xtime`` strings to days since the start of year 1 of the
    365-day calendar

    Parameters
    ----------
    xtime : str, bytes or array-like of str or bytes
        Times such as ``0001-02-01_00:00:00``

    Returns
    -------
    days : float or numpy.ndarray
        The days since ``0001-01-01_00:00:00``
    """
    if isinstance(xtime, (str, bytes)):
        return _one_xtime_to_days(xtime)
    return np.array([_one_xtime_to_days(value) for value in np.ravel(xtime)])


def month_start_days(year, month):
    """
    Get the start of a month, in days since the start of year 1 of the
    365-day calendar

    Parameters
    ----------
    year : int
        The year

    month : int
        The month, from 1 to 12, or 13 for the start of the next year

    Returns
    -------
    days : float
        The days since ``0001-01-01_00:00:00``
    """
    return 365.0 * (year - 1) + float(sum(DAYS_IN_MONTH[: month - 1]))


def days_to_model_year(days):
    """
    Convert days since ``0001-01-01`` to the model year, as time axes show
    it: a date ``YYYY-MM-DD`` is at ``YYYY + (day of year - 1) / 365``, so
    the start of year 18 is at 18

    Parameters
    ----------
    days : float or numpy.ndarray
        Days since ``0001-01-01_00:00:00`` of the 365-day calendar

    Returns
    -------
    year : float or numpy.ndarray
        The model year
    """
    return 1.0 + np.asarray(days, dtype=float) / 365.0


def days_to_date(days):
    """
    Convert days since ``0001-01-01`` to the date they fall on

    Parameters
    ----------
    days : float
        Days since ``0001-01-01_00:00:00`` of the 365-day calendar

    Returns
    -------
    date : str
        The date, as ``YYYY-MM-DD``
    """
    day = int(np.floor(days + 1e-6))
    year, day_of_year = 1 + day // 365, day % 365
    month = 0
    while day_of_year >= DAYS_IN_MONTH[month]:
        day_of_year -= DAYS_IN_MONTH[month]
        month += 1
    return f'{year:04d}-{month + 1:02d}-{day_of_year + 1:02d}'


def _one_xtime_to_days(xtime):
    """Convert one xtime string"""
    if isinstance(xtime, bytes):
        xtime = xtime.decode()
    match = _XTIME.match(xtime)
    if match is None:
        raise ValueError(f'{xtime!r} is not an MPAS xtime.')
    year, month, day, hour, minute, second = (int(g) for g in match.groups())
    seconds = 3600.0 * hour + 60.0 * minute + second
    return month_start_days(year, month) + day - 1 + seconds / 86400.0
