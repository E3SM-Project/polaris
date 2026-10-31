from datetime import datetime

import numpy as np


def get_record_times(xtime):
    """
    Get the time of each record since the first, from MPAS ``xtime`` values

    Parameters
    ----------
    xtime : numpy.ndarray
        The MPAS date strings (``YYYY-MM-DD_hh:mm:ss``) of the records, as
        ``str`` or ``bytes``

    Returns
    -------
    record_times : numpy.ndarray
        The time (s) of each record since the first
    """
    dates = [
        datetime.strptime(_decode(value), '%Y-%m-%d_%H:%M:%S')
        for value in xtime
    ]
    return np.array([(date - dates[0]).total_seconds() for date in dates])


def _decode(value):
    """
    Get an MPAS date string from an xtime value, which may be bytes
    """
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    return str(value).strip()
