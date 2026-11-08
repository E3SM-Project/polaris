"""
Times in E3SM's 365-day calendar, which the MPAS components write as
``xtime`` strings
"""

import re

import numpy as np

#: The days in each month of the 365-day calendar
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

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
