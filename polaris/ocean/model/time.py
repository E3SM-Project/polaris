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
                units=ds['Time'].Units.replace('seconds', 'days'),
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
