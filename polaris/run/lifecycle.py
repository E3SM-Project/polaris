"""
The lifecycle of one step, shared by every way of running one.

`polaris serial` grew this in place, and it is the part that must not differ
between running a suite one step at a time and running its steps at once:
the checks on a step's inputs and outputs, loading what it depends on,
`runtime_setup()`, `run()`, the markers that say it finished, and the
comparisons that say whether it agreed with a baseline.  Moving it here
leaves one copy for both callers rather than a second that drifts.

Nothing here decides *which* step runs or what resources it gets.  That is
the caller's, and it is the whole of the difference between the two.
"""

import os
from typing import Optional

from mpas_tools.logging import LoggingContext, check_call

from polaris.logging import log_method_call
from polaris.run import (
    STEP_COMPLETE_LOG,
    complete_step_run,
    load_dependencies,
)


def run_step(task, step, new_log_file, available_resources, step_log_filename):
    """
    Run the requested step
    """
    logger = task.logger
    cwd = os.getcwd()

    missing_files = list()
    for input_file in step.inputs:
        if not os.path.exists(input_file):
            missing_files.append(input_file)

    if len(missing_files) > 0:
        raise OSError(
            f'input file(s) missing in step {step.name} in '
            f'{step.component.name}/{step.subdir}: {missing_files}'
        )

    load_dependencies(step)

    # each logger needs a unique name
    logger_name = step.path.replace('/', '_')
    if new_log_file:
        # we want to create new log file and point the step to that name
        new_log_filename = f'{cwd}/{step.name}.log'
        step_log_filename = new_log_filename
        step_logger = None
    else:
        # either we don't want a log file at all or there is an existing one
        # to use.  Either way, we don't want a new log filename and we want
        # to use the existing logger.  The step log filename will be whatever
        # is passed as a parameter
        step_logger = logger
        new_log_filename = None

    step.log_filename = step_log_filename

    with LoggingContext(
        name=logger_name, logger=step_logger, log_filename=new_log_filename
    ) as step_logger:
        step.logger = step_logger
        os.chdir(step.work_dir)

        step_logger.info('')
        log_method_call(method=step.constrain_resources, logger=step_logger)
        step_logger.info('')
        # a step confined to part of the allocation has to be told about
        # that part, not about the whole job.  Nothing assigns a placement
        # yet, so this is the whole job in every case today.
        if step.placement is not None:
            step_resources = step.component.get_available_resources(
                step.placement
            )
        else:
            step_resources = available_resources
        step.constrain_resources(step_resources)

        # runtime_setup() will perform small tasks that require knowing the
        # resources of the task before the step runs (such as creating
        # graph partitions)
        step_logger.info('')
        log_method_call(method=step.runtime_setup, logger=step_logger)
        step_logger.info('')
        step.runtime_setup()

        if step.args is not None:
            step_logger.info(
                "\nBypassing step's run() method and running "
                'with command line args\n'
            )
            for args in step.args:
                log_method_call(
                    method=step.component.run_parallel_command,
                    logger=step_logger,
                )
                step_logger.info('')
                step.component.run_parallel_command(
                    args,
                    step.cpus_per_task,
                    step.ntasks,
                    step.openmp_threads,
                    step.logger,
                    gpus=step.gpus,
                    placement=step.placement,
                    memory_cap=step.memory,
                )
        else:
            step_logger.info('')
            log_method_call(method=step.run, logger=step_logger)
            step_logger.info('')
            step.run()

    complete_step_run(step)

    missing_files = list()
    for output_file in step.outputs:
        if not os.path.exists(output_file):
            missing_files.append(output_file)

    if len(missing_files) > 0:
        # We want to indicate that the step failed by removing the pickle
        try:
            os.remove('step_after_run.pickle')
        except FileNotFoundError:
            pass
        raise OSError(
            f'output file(s) missing in step {step.name} in '
            f'{step.component.name}/{step.subdir}: {missing_files}'
        )


def step_is_complete(step) -> bool:
    """
    Whether a step has already run successfully in its work directory.

    A step that has is skipped rather than run again, which is what makes a
    rerun after a failure resume from what succeeded.

    Parameters
    ----------
    step : polaris.Step
        The step to ask about

    Returns
    -------
    complete : bool
        Whether the step left the marker that says it finished
    """
    return os.path.exists(os.path.join(step.work_dir, STEP_COMPLETE_LOG))


def run_step_as_subprocess(logger, step, new_log_file):
    """
    Run the requested step as a subprocess
    """
    cwd = os.getcwd()
    logger_name = step.path.replace('/', '_')
    if new_log_file:
        log_filename = f'{cwd}/{step.name}.log'
        step_logger = None
    else:
        step_logger = logger
        log_filename = None

    step.log_filename = log_filename

    with LoggingContext(
        name=logger_name, logger=step_logger, log_filename=log_filename
    ) as step_logger:
        os.chdir(step.work_dir)
        step_args = ['polaris', 'serial', '--step_is_subprocess']
        check_call(step_args, step_logger)


def read_baseline_status_from_logs(step_work_dir: str) -> Optional[bool]:
    """Get baseline comparison status from existing log markers.

    Returns
    -------
    Optional[bool]
        True if ``baseline_passed.log`` exists, False if
        ``baseline_failed.log`` exists, otherwise None.
    """
    baseline_pass_filename = os.path.join(step_work_dir, 'baseline_passed.log')
    baseline_fail_filename = os.path.join(step_work_dir, 'baseline_failed.log')

    if os.path.exists(baseline_pass_filename):
        return True
    if os.path.exists(baseline_fail_filename):
        return False
    return None


def read_property_status_from_logs(step_work_dir: str) -> Optional[bool]:
    """Get property check status from existing log markers.

    Returns
    -------
    Optional[bool]
        True if ``property_check_passed.log`` exists, False if
        ``property_check_failed.log`` exists, otherwise None.
    """
    property_check_pass_filename = os.path.join(
        step_work_dir, 'property_check_passed.log'
    )
    property_check_fail_filename = os.path.join(
        step_work_dir, 'property_check_failed.log'
    )

    if os.path.exists(property_check_pass_filename):
        return True
    if os.path.exists(property_check_fail_filename):
        return False
    return None


def accumulate_baselines(
    baselines_passed: Optional[bool], status: bool
) -> Optional[bool]:
    """Aggregate baseline results across steps.

    None means no baseline comparisons were performed. If any comparison fails,
    the aggregate becomes False.
    """
    if baselines_passed is None:
        return status
    return baselines_passed and status
