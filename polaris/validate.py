import os

import numpy as np
import xarray as xr


def compare_variables(variables, filename1, filename2, logger, l1_norm=0.0,
                      l2_norm=0.0, linf_norm=0.0, quiet=True, ds1=None,
                      ds2=None):
    """
    compare variables in the two files

    Parameters
    ----------
    variables : list
        A list of variable names to compare

    filename1 : str
        The relative path to a file within the ``work_dir``.  If ``filename2``
        is also given, comparison will be performed with ``variables`` in that
        file.  If a baseline directory was provided when setting up the
        test case, the ``variables`` will be compared between this test case
        and the same relative filename in the baseline version of the test
        case.

    filename2 : str
        The relative path to another file within the ``work_dir`` if comparing
        between files within the current test case.  If a baseline directory
        was provided, the ``variables`` from this file will also be compared
        with those in the corresponding baseline file.

    logger: logging.Logger
        The logger to log validation output to

    l1_norm : float, optional
        The maximum allowed L1 norm difference between the variables in
        ``filename1`` and ``filename2``.  To skip L1 norm check, pass None.

    l2_norm : float, optional
        The maximum allowed L2 norm difference between the variables in
        ``filename1`` and ``filename2``.  To skip L2 norm check, pass None.

    linf_norm : float, optional
        The maximum allowed L-Infinity norm difference between the variables in
        ``filename1`` and ``filename2``.  To skip Linf norm check, pass None.

    quiet : bool, optional
        Whether to print detailed information.  If quiet is False, the norm
        tolerance values being compared against will be printed when the
        comparison is made.  This is generally desirable when using nonzero
        norm tolerance values.

    ds1 : xarray.Dataset, optional
        A dataset loaded from filename1.  This may save time if the dataset is
        already loaded and allows for calculations to be performed or variables
        to be renamed if necessary.

    ds2 : xarray.Dataset, optional
        A dataset loaded from filename2.  This may save time if the dataset is
        already loaded and allows for calculations to be performed or variables
        to be renamed if necessary.

    Returns
    -------
    all_pass : bool
        Whether all variables passed the validation checks

    """

    for filename in [filename1, filename2]:
        if not os.path.exists(filename):
            logger.error(f'File {filename} does not exist.')
            return False

    if ds1 is None:
        ds1 = xr.open_dataset(filename1)

    if ds2 is None:
        ds2 = xr.open_dataset(filename2)

    all_pass = True

    for variable in variables:
        if not _all_found(ds1, filename1, ds2, filename2, variable, logger):
            all_pass = False
            continue

        da1 = ds1[variable]
        da2 = ds2[variable]

        if not np.all(da1.dims == da2.dims):
            logger.error(f"Dimensions for variable {variable} don't match "
                         f"between files {filename1} and {filename2}.")
            all_pass = False
            continue

        if not _all_sizes_match(da1, filename1, da2, filename2, variable,
                                logger):
            all_pass = False
            continue

        if not quiet:
            print("    Pass thresholds are:")
            if l1_norm is not None:
                print(f"       L1: {l1_norm:16.14e}")
            if l2_norm is not None:
                print(f"       L2: {l2_norm:16.14e}")
            if linf_norm is not None:
                print(f"       L_Infinity: {linf_norm:16.14e}")
        variable_pass = True
        if 'Time' in da1.dims:
            time_range = range(0, da1.sizes['Time'])
            time_str = ', '.join([f'{j}' for j in time_range])
            print(f'{variable.ljust(20)} Time index: {time_str}')
            for time_index in time_range:
                slice1 = da1.isel(Time=time_index)
                slice2 = da2.isel(Time=time_index)
                result = _compute_norms(slice1, slice2, quiet, l1_norm,
                                        l2_norm, linf_norm,
                                        time_index=time_index)
                variable_pass = variable_pass and result

        else:
            print(f'{variable}')
            result = _compute_norms(da1, da2, quiet, l1_norm, l2_norm,
                                    linf_norm)
            variable_pass = variable_pass and result

        # ANSI fail text: https://stackoverflow.com/a/287944/7728169
        start_fail = '\033[91m'
        start_pass = '\033[92m'
        end = '\033[0m'
        pass_str = f'{start_pass}PASS{end}'
        fail_str = f'{start_fail}FAIL{end}'

        if variable_pass:
            print(f'  {pass_str} {filename1}\n')
        else:
            print(f'  {fail_str} {filename1}\n')
        print(f'       {filename2}\n')
        all_pass = all_pass and variable_pass

    return all_pass


def _all_found(ds1, filename1, ds2, filename2, variable, logger):
    """ Is the variable found in both datasets? """
    all_found = True
    for ds, filename in [(ds1, filename1), (ds2, filename2)]:
        if variable not in ds:
            logger.error(f'Variable {variable} not in {filename}.')
            all_found = False
    return all_found


def _all_sizes_match(da1, filename1, da2, filename2, variable, logger):
    """ Do all dimension sizes match between the two variables? """
    all_match = True
    for dim in da1.sizes:
        if da1.sizes[dim] != da2.sizes[dim]:
            logger.error(f"Field sizes for variable {variable} don't "
                         f"match files {filename1} and {filename2}.")
            all_match = False
    return all_match


def _compute_norms(da1, da2, quiet, max_l1_norm, max_l2_norm, max_linf_norm,
                   time_index=None):
    """ Compute norms between variables in two DataArrays """

    da1 = _rename_duplicate_dims(da1)
    da2 = _rename_duplicate_dims(da2)

    result = True
    diff = np.abs(da1 - da2).values.ravel()
    # skip entries where one field or both are a fill value
    diff = diff[np.isfinite(diff)]

    l1_norm = np.linalg.norm(diff, ord=1)
    l2_norm = np.linalg.norm(diff, ord=2)
    linf_norm = np.linalg.norm(diff, ord=np.inf)

    if time_index is None:
        diff_str = ''
    else:
        diff_str = f'{time_index:d}: '

    if max_l1_norm is not None:
        if max_l1_norm < l1_norm:
            result = False
    diff_str = f'{diff_str} l1: {l1_norm:16.14e} '

    if max_l2_norm is not None:
        if max_l2_norm < l2_norm:
            result = False
    diff_str = f'{diff_str} l2: {l2_norm:16.14e} '

    if max_linf_norm is not None:
        if max_linf_norm < linf_norm:
            result = False
    diff_str = f'{diff_str} linf: {linf_norm:16.14e} '

    if not quiet or not result:
        print(diff_str)

    return result


def _rename_duplicate_dims(da):
    dims = list(da.dims)
    new_dims = list(dims)
    duplicates = False
    for index, dim in enumerate(dims):
        if dim in dims[index + 1:]:
            duplicates = True
            suffix = 2
            for other_index, other in enumerate(dims[index + 1:]):
                if other == dim:
                    new_dims[other_index + index + 1] = f'{dim}_{suffix}'
                    suffix += 1

    if not duplicates:
        return da

    da = xr.DataArray(data=da.values, dims=new_dims)
    return da
