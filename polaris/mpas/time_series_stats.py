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
        new_name = name[len(prefix) :].rsplit('_', 1)[-1]
        if new_name in renames.values() or new_name in ds.data_vars:
            raise ValueError(
                f'Renaming {name} to {new_name} would collide with another '
                f'variable.'
            )
        renames[name] = new_name
    return ds.rename(renames)
