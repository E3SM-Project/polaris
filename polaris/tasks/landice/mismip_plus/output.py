import numpy as np
import xarray as xr

# the days before each month in MALI's 365-day calendar
DAYS_BEFORE_MONTH = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30])


def read_output(filename):
    """
    Read one of MALI's output files with its time in years as the coordinate.
    A run that continues from a restart may write some times again, so only
    the last record at each time is kept, in time order.

    Parameters
    ----------
    filename : str
        A MALI output file with ``xtime``, such as ``output.nc`` or
        ``globalStats.nc``

    Returns
    -------
    ds : xarray.Dataset
        The output with a ``Time`` coordinate in years
    """
    ds = xr.open_dataset(filename)
    years = np.array([_years(_decode(value)) for value in ds.xtime.values])
    # the index of the last record at each time, in time order
    _, reversed_indices = np.unique(years[::-1], return_index=True)
    indices = len(years) - 1 - reversed_indices
    ds['Time'] = ('Time', years)
    ds.Time.attrs['units'] = 'years'
    return ds.isel(Time=indices)


def _decode(value):
    """
    Decode one of MALI's times, which may be bytes or an array of characters
    """
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.ndarray):
        return b''.join(value.tolist()).decode()
    return str(value)


def _years(xtime):
    """
    Convert one of MALI's times to years
    """
    date, clock = xtime.strip().split('_')
    year, month, day = (int(value) for value in date.split('-'))
    hour, minute, second = (float(value) for value in clock.split(':'))
    days = (
        DAYS_BEFORE_MONTH[month - 1]
        + day
        - 1
        + (hour + (minute + second / 60.0) / 60.0) / 24.0
    )
    return year + days / 365.0
