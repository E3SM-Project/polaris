import re
import time

import numpy as np


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


def get_time_step_string(days=None, seconds=None, time_str=None):
    """Format a time step for model config options.

    Omega currently requires the day prefix and underscore (e.g.
    ``0000_00:10:00``) and will misinterpret ``hh:mm:ss``.

    Parameters
    ----------
    days : float, optional
        A time interval in days

    seconds : float, optional
        A time interval in seconds

    time_str : str, optional
        An existing time string in either ``hh:mm:ss`` or ``DDDD_hh:mm:ss``
        format (optionally with a decimal fraction of seconds).

    Returns
    -------
    time_step : str
        The time step as a string in the format ``DDDD_HH:MM:SS``.
    """
    if time_str is not None:
        stripped = str(time_str).strip()
        with_day = re.match(
            (
                r'^(?P<days>\d+)_(?P<hours>\d+):(?P<minutes>\d{2}):'
                r'(?P<seconds>\d{2})(?:\.(?P<fraction>\d+))?$'
            ),
            stripped,
        )
        without_day = re.match(
            (
                r'^(?P<hours>\d+):(?P<minutes>\d{2}):'
                r'(?P<seconds>\d{2})(?:\.(?P<fraction>\d+))?$'
            ),
            stripped,
        )

        if with_day is None and without_day is None:
            raise ValueError(
                'Unrecognized time string format. Expected hh:mm:ss or '
                'DDDD_hh:mm:ss (optionally with .sss) but got: '
                f'{time_str}'
            )

        match = with_day if with_day is not None else without_day
        assert match is not None
        parsed_days = int(match.groupdict().get('days') or 0)
        parsed_hours = int(match.group('hours'))
        parsed_minutes = int(match.group('minutes'))
        parsed_seconds = int(match.group('seconds'))

        total_seconds = (
            parsed_days * 86400
            + parsed_hours * 3600
            + parsed_minutes * 60
            + parsed_seconds
        )
        seconds = float(total_seconds)
        days = None

    sec_per_day = 86400
    total = 0.0
    if seconds is not None:
        total += seconds
    if days is not None:
        total += sec_per_day * days

    if total < 0.0:
        raise ValueError('Time step must be non-negative')

    total_int = int(total)
    day_part, sec_part = divmod(total_int, sec_per_day)
    hour_part, sec_part = divmod(sec_part, 3600)
    minute_part, second_part = divmod(sec_part, 60)

    return (
        f'{day_part:04d}_{hour_part:02d}:{minute_part:02d}:{second_part:02d}'
    )
