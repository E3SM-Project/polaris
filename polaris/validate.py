import fnmatch
import os
import re

import numpy
import xarray


def compare_variables(task, variables, filename1, filename2=None,
                      l1_norm=0.0, l2_norm=0.0, linf_norm=0.0, quiet=True,
                      check_outputs=True, skip_if_step_not_run=True):
    """
    Compare variables between files in the current task and/or with the
    baseline results.  The results of the comparison are added to the
    task's "validation" dictionary, which the framework can use later to
    log the task results and/or to raise an exception to indicate that
    the task has failed.

    Parameters
    ----------
    task : polaris.Task
        An object describing a task to validate

    variables : list
        A list of variable names to compare

    filename1 : str
        The relative path to a file within the ``work_dir``.  If ``filename2``
        is also given, comparison will be performed with ``variables`` in that
        file.  If a baseline directory was provided when setting up the
        task, the ``variables`` will be compared between this task
        and the same relative filename in the baseline version of the task.

    filename2 : str, optional
        The relative path to another file within the ``work_dir`` if comparing
        between files within the current task.  If a baseline directory
        was provided, the ``variables`` from this file will also be compared
        with those in the corresponding baseline file.

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

    check_outputs : bool, optional
        Whether to check to make sure files are valid outputs of steps in
        the task.  This should be set to ``False`` if comparing with an
        output of a step in another task.

    skip_if_step_not_run : bool, optional
        Whether to skip the variable comparison if a user did not run one (or
        both) of the steps involved in the comparison.  This would happen if
        users are running steps individually or has edited ``steps_to_run``
        in the config file to exclude one of the steps.
    """
    work_dir = task.work_dir

    logger = task.logger

    path1 = os.path.abspath(os.path.join(work_dir, filename1))
    if filename2 is not None:
        path2 = os.path.abspath(os.path.join(work_dir, filename2))
    else:
        path2 = None

    if check_outputs:
        all_steps_run = _check_for_outputs(
            task, logger, path1, path2, filename1, filename2)

    if skip_if_step_not_run and not all_steps_run:
        return

    if task.validation is not None:
        validation = task.validation
    else:
        validation = {'internal_pass': None,
                      'baseline_pass': None}

    if filename2 is not None:
        internal_pass = _compare_variables(
            variables, path1, path2, l1_norm, l2_norm, linf_norm, quiet,
            logger)

        if validation['internal_pass'] is None:
            validation['internal_pass'] = internal_pass
        else:
            validation['internal_pass'] = \
                validation['internal_pass'] and internal_pass

    if task.baseline_dir is not None:
        baseline_root = task.baseline_dir
        baseline_pass = True

        result = _compare_variables(
            variables, os.path.join(work_dir, filename1),
            os.path.join(baseline_root, filename1), l1_norm=0.0, l2_norm=0.0,
            linf_norm=0.0, quiet=quiet, logger=logger)
        baseline_pass = baseline_pass and result

        if filename2 is not None:
            result = _compare_variables(
                variables, os.path.join(work_dir, filename2),
                os.path.join(baseline_root, filename2), l1_norm=0.0,
                l2_norm=0.0, linf_norm=0.0, quiet=quiet, logger=logger)
            baseline_pass = baseline_pass and result

        if validation['baseline_pass'] is None:
            validation['baseline_pass'] = baseline_pass
        else:
            validation['baseline_pass'] = \
                validation['baseline_pass'] and baseline_pass

    task.validation = validation


def compare_timers(task, timers, rundir1, rundir2=None):
    """
    Compare variables between files in the current task and/or with the
    baseline results.

    Parameters
    ----------
    task : polaris.Task
        An object describing a task to validate

    timers : list
        A list of timer names to compare

    rundir1 : str
        The relative path to a directory within the ``work_dir``. If
        ``rundir2`` is also given, comparison will be performed with ``timers``
        in that file.  If a baseline directory was provided when setting up the
        task, the ``timers`` will be compared between this task and
        the same relative directory under the baseline version of the task.

    rundir2 : str, optional
        The relative path to another file within the ``work_dir`` if comparing
        between files within the current task.  If a baseline directory
        was provided, the ``timers`` from this file will also be compared with
        those in the corresponding baseline directory.
    """

    work_dir = task.work_dir
    baseline_root = task.baseline_dir

    if rundir2 is not None:
        _compute_timers(os.path.join(work_dir, rundir1),
                        os.path.join(work_dir, rundir2), timers)

    if baseline_root is not None:
        _compute_timers(os.path.join(baseline_root, rundir1),
                        os.path.join(work_dir, rundir1), timers)

        if rundir2 is not None:
            _compute_timers(os.path.join(baseline_root, rundir2),
                            os.path.join(work_dir, rundir2), timers)


def _check_for_outputs(task, logger, path1, path2, filename1, filename2):
    """ Check for outputs for each step from one or two run directories """

    all_steps_run = True
    file1_found = False
    file2_found = False
    step_name1 = None
    step_name2 = None
    for step_name, step in task.steps.items():
        for output in step.outputs:
            # outputs are already absolute paths combined with the step dir
            if output == path1:
                file1_found = True
                step_name1 = step_name
            if output == path2:
                file2_found = True
                step_name2 = step_name

    if not file1_found:
        raise ValueError(f'{filename1} does not appear to be an output of any '
                         'step in this task.')
    if filename2 is not None and not file2_found:
        raise ValueError(f'{filename2} does not appear to be an output of any '
                         'step in this task.')

    step1_not_run = (file1_found and
                     step_name1 not in task.steps_to_run)
    step2_not_run = (file2_found and
                     step_name2 not in task.steps_to_run)

    if step1_not_run and step2_not_run:
        logger.info(f'Skipping validation because {step_name1} and '
                    f'{step_name2} weren\'t  run')
    elif step1_not_run:
        logger.info(f'Skipping validation because {step_name1} wasn\'t run')
    elif step2_not_run:
        logger.info(f'Skipping validation because {step_name2} wasn\'t run')
    if step1_not_run or step2_not_run:
        all_steps_run = False

    return all_steps_run


def _compare_variables(variables, filename1, filename2, l1_norm, l2_norm,
                       linf_norm, quiet, logger):
    """ compare fields in the two files """

    for filename in [filename1, filename2]:
        if not os.path.exists(filename):
            logger.error(f'File {filename} does not exist.')
            return False

    ds1 = xarray.open_dataset(filename1)
    ds2 = xarray.open_dataset(filename2)

    all_pass = True

    for variable in variables:
        all_found = True
        for ds, filename in [(ds1, filename1), (ds2, filename2)]:
            if variable not in ds:
                logger.error(f'Variable {variable} not in {filename}.')
                all_found = False
        if not all_found:
            all_pass = False
            continue

        da1 = ds1[variable]
        da2 = ds2[variable]

        if not numpy.all(da1.dims == da2.dims):
            logger.error(f"Dimensions for variable {variable} don't match "
                         f"between files {filename1} and {filename2}.")
            all_pass = False
            continue

        all_match = True
        for dim in da1.sizes:
            if da1.sizes[dim] != da2.sizes[dim]:
                logger.error(f"Field sizes for variable {variable} don't "
                             f"match files {filename1} and {filename2}.")
                all_match = False
        if not all_match:
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


def _compute_norms(da1, da2, quiet, max_l1_norm, max_l2_norm, max_linf_norm,
                   time_index=None):
    """ Compute norms between variables in two DataArrays """

    da1 = _rename_duplicate_dims(da1)
    da2 = _rename_duplicate_dims(da2)

    result = True
    diff = numpy.abs(da1 - da2).values.ravel()
    # skip entries where one field or both are a fill value
    diff = diff[numpy.isfinite(diff)]

    l1_norm = numpy.linalg.norm(diff, ord=1)
    l2_norm = numpy.linalg.norm(diff, ord=2)
    linf_norm = numpy.linalg.norm(diff, ord=numpy.inf)

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


def _compute_timers(base_directory, comparison_directory, timers):
    """ Find timers and compute speedup between two run directories """
    for timer in timers:
        timer1_found, timer1 = _find_timer_value(timer, base_directory)
        timer2_found, timer2 = _find_timer_value(timer, comparison_directory)

        if timer1_found and timer2_found:
            if timer2 > 0.:
                speedup = timer1 / timer2
            else:
                speedup = 1.0

            percent = (timer2 - timer1) / timer1

            print(f"Comparing timer {timer}:")
            print(f"             Base: {timer1}")
            print(f"          Compare: {timer2}")
            print(f"   Percent Change: {percent * 100}%")
            print(f"          Speedup: {speedup}")


def _find_timer_value(timer_name, directory):
    """ Find a timer in the given directory """
    # Build a regular expression for any two characters with a space between
    # them.
    regex = re.compile(r'(\S) (\S)')

    sub_timer_name = timer_name.replace(' ', '_')

    timer = 0.0
    timer_found = False
    for file in os.listdir(directory):
        if not timer_found:
            # Compare files written using built in MPAS timers
            if fnmatch.fnmatch(file, "log.*.out"):
                timer_line_size = 6
                name_index = 1
                total_index = 2
            # Compare files written using GPTL timers
            elif fnmatch.fnmatch(file, "timing.*"):
                timer_line_size = 6
                name_index = 0
                total_index = 3
            else:
                continue

            with open(os.path.join(directory, file), "r") as stats_file:
                for block in iter(lambda: stats_file.readline(), ""):
                    new_block = regex.sub(r"\1_\2", block[2:])
                    new_block_arr = new_block.split()
                    if len(new_block_arr) >= timer_line_size:
                        if sub_timer_name.find(new_block_arr[name_index]) >= 0:
                            try:
                                timer = \
                                    timer + float(new_block_arr[total_index])
                                timer_found = True
                            except ValueError:
                                pass

    return timer_found, timer


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

    da = xarray.DataArray(data=da.values, dims=new_dims)
    return da
