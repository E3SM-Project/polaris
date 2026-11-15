import xarray as xr

#: The prefix of the fields that MPAS-Ocean's monthly time-series statistics
#: write
MONTHLY_PREFIX = 'timeMonthly_avg_'


def rename_time_series_stats(ds, prefix=MONTHLY_PREFIX):
    """
    Rename the time means of MPAS's time-series statistics to the names of
    the fields they average

    MPAS writes the monthly mean of ``ssh`` as ``timeMonthly_avg_ssh``, and
    that of a member of a variable array, such as ``temperature`` in
    ``activeTracers``, as ``timeMonthly_avg_activeTracers_temperature``.
    Both become the field's own name, so that the same diagnostics read
    monthly means and snapshots.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset of time-series statistics

    prefix : str, optional
        The prefix of the time means

    Returns
    -------
    ds : xarray.Dataset
        The dataset with the time means renamed and other variables
        unchanged
    """
    renames: dict = dict()
    for name in ds.data_vars:
        if not name.startswith(prefix):
            continue
        new_name = _stats_field_name(name, prefix)
        if new_name in renames.values() or new_name in ds.data_vars:
            raise ValueError(
                f'Renaming {name} to {new_name} would collide with another '
                f'variable.'
            )
        renames[name] = new_name
    return ds.rename(renames)


def read_time_series(filenames, names=None, prefix=None, chunk=False):
    """
    Read fields from a series of MPAS output files, one file at a time

    Each file is opened once, the fields kept are loaded and the file is
    closed.  Reading many files this way neither holds them all open nor
    reopens them, as loading a dataset combined from more files than
    xarray keeps open would, once for each variable.

    Parameters
    ----------
    filenames : list of str
        The files, in order

    names : list of str, optional
        The fields to keep, by their names after renaming if ``prefix`` is
        given.  A field a file lacks is skipped in that file.  By default,
        every variable is kept.

    prefix : str, optional
        The prefix of time-series statistics, such as ``timeMonthly_avg_``.
        If given, the time means are renamed as by
        :py:func:`rename_time_series_stats`, and the variables along
        ``Time`` without the prefix, such as ``xtime_startMonthly``, are
        kept as well.

    chunk : bool, optional
        Whether to keep each file's fields as one chunk of a dask array,
        so that a field that only some files have, and computations on the
        series, are not held in memory for all the files at once

    Returns
    -------
    ds : xarray.Dataset
        The fields, concatenated along ``Time``, with any variables without
        ``Time`` from the first file
    """
    datasets = []
    for filename in filenames:
        with xr.open_dataset(filename, decode_times=False) as ds:
            keep = [
                name
                for name in ds.data_vars
                if _keep_variable(ds[name], names, prefix)
            ]
            ds_file = ds[keep].load()
        if chunk:
            ds_file = ds_file.chunk()
        datasets.append(ds_file)
    ds = xr.concat(
        datasets,
        dim='Time',
        data_vars='minimal',
        coords='minimal',
        compat='override',
        combine_attrs='override',
    )
    if prefix is not None:
        ds = rename_time_series_stats(ds, prefix=prefix)
    return ds


def _keep_variable(variable, names, prefix):
    """Whether to keep a variable in reading a time series"""
    if names is None:
        return True
    name = str(variable.name)
    if prefix is not None and name.startswith(prefix):
        return _stats_field_name(name, prefix) in names
    if name in names:
        return True
    # the time, bounds and counts of time-series statistics
    return prefix is not None and 'Time' in variable.dims


def _stats_field_name(name, prefix):
    """The name of the field a time-series statistic averages"""
    return name[len(prefix) :].rsplit('_', 1)[-1]
