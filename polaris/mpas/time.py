import datetime
import time

import numpy as np


def time_index_from_xtime(xtime, dt_target, start_xtime=None):
    """
    Determine the time index closest to the target time

    Parameters
    ----------
    xtime : numpy.ndarray of numpy.char
        Times in the dataset

    dt_target : float
        Time in seconds since the first time in the list of ``xtime`` values

    start_xtime : str, optional
        The start time, the first entry in ``xtime`` by default

    Returns
    -------
    time_index : int
        Index in xtime that is closest to dt_target
    """
    dt = time_since_start(xtime, start_xtime)
    time_index = np.argmin(np.abs(np.subtract(dt, dt_target)))
    return time_index


def time_since_start(xtime, start_xtime='0001-01-01_01:00:00'):
    """
    Determine the time elapsed since the start of the simulation

    Parameters
    ----------
    xtime : numpy.ndarray of numpy.char
        Times in the dataset

    start_xtime : str, optional
        The start time, the first entry in ``xtime`` by default

    Returns
    -------
    dt : numpy.ndarray
        The elapsed time in seconds corresponding to each entry in xtime
    """
    if start_xtime is None:
        start_xtime = xtime[0].decode()

    try:
        time_format = '%Y-%m-%d_%H:%M:%S.%f'
        t0 = datetime.datetime.strptime(start_xtime, time_format)
    except ValueError:
        time_format = '%Y-%m-%d_%H:%M:%S'
        t0 = datetime.datetime.strptime(start_xtime, time_format)
    dt = np.zeros((len(xtime),))
    for idx, xt in enumerate(xtime):
        t = datetime.datetime.strptime(xt.decode(), time_format)
        dt[idx] = (t - t0).total_seconds()
    return dt


def get_time_interval_string(days=None, seconds=None):
    """
    Convert a time interval in days and/or seconds to a string for use in a
    model config option.  If both are provided, they will be added

    This is the inverse of :py:func:`duration_to_seconds`.

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


def duration_to_seconds(duration):
    """
    Convert an MPAS-style time-interval string to a number of seconds

    This is the inverse of :py:func:`get_time_interval_string`.

    Parameters
    ----------
    duration : str
        A time interval in the format ``DDDD_HH:MM:SS.SSS``, where the
        ``DDDD_`` day prefix and the fractional seconds are both optional

    Returns
    -------
    seconds : float
        The time interval in seconds
    """
    if '_' in duration:
        days_str, time_of_day = duration.split('_')
        days = int(days_str)
    else:
        days = 0
        time_of_day = duration
    hours, minutes, seconds = time_of_day.split(':')
    return (
        days * 86400.0
        + int(hours) * 3600.0
        + int(minutes) * 60.0
        + float(seconds)
    )


def duration_to_omega_period(duration):
    """
    Convert an MPAS-style time-interval string to an Omega period string

    Omega spells an analysis period as a count followed by a unit, e.g.
    ``1Day`` or ``6Hour``.  It splits the string at the first non-digit and
    appends an ``s`` to the unit if there is not one already, so both
    ``6Hour`` and ``6Hours`` name the same period.  The string is also echoed
    verbatim into the name of the file the analysis group writes
    (``<prefix>_<period>Instants`` for a snapshot period, or
    ``<prefix>_<period>TimeStats`` for a reduction period), so whatever is put
    in the config has to be the same string used to find the output later.

    The largest unit that divides the interval exactly is used, since that is
    the form a reader expects: one day rather than 24 hours.

    Parameters
    ----------
    duration : str
        A time interval in the format ``DDDD_HH:MM:SS.SSS``, where the
        ``DDDD_`` day prefix and the fractional seconds are both optional

    Returns
    -------
    period : str
        The interval as an Omega period string, e.g. ``'1Day'``

    Raises
    ------
    ValueError
        If the interval is not a positive whole number of seconds
    """
    seconds = duration_to_seconds(duration)
    if seconds <= 0 or seconds != int(seconds):
        raise ValueError(
            f'An Omega period must be a positive whole number of seconds, '
            f'but {duration!r} is {seconds} s.'
        )
    seconds = int(seconds)
    for unit_seconds, unit in [
        (86400, 'Day'),
        (3600, 'Hour'),
        (60, 'Minute'),
        (1, 'Second'),
    ]:
        if seconds % unit_seconds == 0:
            return f'{seconds // unit_seconds}{unit}'
    # unreachable: every whole number of seconds is divisible by 1
    raise AssertionError(f'Could not express {duration!r} as an Omega period')
