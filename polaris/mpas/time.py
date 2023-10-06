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
    if start_xtime is None:
        start_xtime = xtime[0].decode()

    t0 = datetime.datetime.strptime(start_xtime, '%Y-%m-%d_%H:%M:%S')
    dt = np.zeros((len(xtime),))
    for idx, xt in enumerate(xtime):
        t = datetime.datetime.strptime(xt.decode(),
                                       '%Y-%m-%d_%H:%M:%S')
        dt[idx] = (t - t0).total_seconds()
    time_index = np.argmin(np.abs(np.subtract(dt, dt_target)))
    return time_index
