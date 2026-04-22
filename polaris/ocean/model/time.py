import time
from datetime import datetime

import numpy as np
import pandas as pd


def get_days_since_start(ds):
    """
    Ocean model output may or may not include 'daysSinceStartOfSim'. This
    routine uses 'daysSinceStartOfSim' if available, otherwise it uses 'Time'
    """
    if 'daysSinceStartOfSim' in ds.keys():
        t_arr = ds.daysSinceStartOfSim.values.astype(float)
    elif 'xtime' in ds.keys():
        timestamps = []
        for time_str in ds.xtime.values.astype(str):
            try:
                timestamp = datetime.strptime(time_str, '%Y-%m-%d_%H:%M:%S.%f')
            except ValueError:
                timestamp = datetime.strptime(time_str, '%Y-%m-%d_%H:%M:%S')
            timestamps.append(timestamp)
        # Calculate seconds since the first timestamp
        seconds_since_start = [
            (ts - timestamps[0]).total_seconds() for ts in timestamps
        ]
        t_arr = np.array(seconds_since_start, dtype=float) / 86400.0
    elif 'Time' in ds.keys():
        t_vals = ds['Time'].values
        t_pd = pd.to_datetime(t_vals)
        t_arr = 1.0e9 * (t_pd - t_pd[0]) / np.timedelta64(1, 's')
        t_arr = t_arr.astype(float) / 86400.0
    else:
        raise ValueError('Could not find a time variable in dataset')
    return t_arr


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
