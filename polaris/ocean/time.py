import numpy as np
import pandas as pd


def get_days_since_start(ds):
    """
    Ocean model output may or may not include 'daysSinceStartOfSim'. This
    routine uses 'daysSinceStartOfSim' if available, otherwise it uses 'Time'
    """
    if 'daysSinceStartOfSim' in ds.keys():
        t_arr = ds.daysSinceStartOfSim.values.astype(float)
    elif 'Time' in ds.keys():
        t_vals = ds['Time'].values
        t_pd = pd.to_datetime(t_vals)
        t_arr = 1.0e9 * (t_pd - t_pd[0]) / np.timedelta64(1, 's')
        t_arr = t_arr.astype(float) / 86400.0
    else:
        raise ValueError('Could not find a time variable in dataset')
    return t_arr
