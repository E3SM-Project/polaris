import datetime

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
