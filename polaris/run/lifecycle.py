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

import json
import os
from typing import Dict, Optional

from mpas_tools.logging import LoggingContext, check_call

from polaris.logging import log_method_call
from polaris.parallel import launching_step_command
from polaris.run import (
    STEP_COMPLETE_LOG,
    complete_step_run,
    load_dependencies,
)
from polaris.run.confinement import check_confinement
from polaris.run.memory import format_bytes
from polaris.run.pieces import PIECES_SUMMARY, Pieces, slots_from
from polaris.run.residents import serial_resources


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

    dependency_pickles = load_dependencies(step)

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

        _log_dependency_pickles(dependency_pickles, step_logger)

        step_logger.info('')
        log_method_call(method=step.constrain_resources, logger=step_logger)
        step_logger.info('')
        # a step confined to part of the allocation has to be told about
        # that part, not about the whole job.  A serial run assigns no
        # placement, so there it is the whole job as it always was.
        if step.placement is not None:
            step_resources = step.component.get_available_resources(
                step.placement
            )
        else:
            step_resources = available_resources
        step.constrain_resources(step_resources)
        _log_sizing(step, step_resources, step_logger, 'after sizing')

        # a placement is a promise about part of the machine, and nothing
        # enforces it.  Ask, once, whether this step got what it was given.
        check_confinement(step, step_logger)

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
                _log_sizing(step, step_resources, step_logger, 'at launch')
                with launching_step_command():
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
        elif step.hands_out_work:
            step_logger.info('')
            log_method_call(method=step.run_pieces, logger=step_logger)
            step_logger.info('')
            _run_pieces(step)
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


def read_baseline_diff_summary_from_logs(step_work_dir: str) -> Dict:
    """Get the baseline diff summary from an existing JSON file, if any.

    Returns
    -------
    dict
        The maximum l1, l2 and l_infinity norm differences for each
        variable, keyed by variable name, or an empty dict if no summary
        is available.
    """
    filename = os.path.join(step_work_dir, 'baseline_diff_summary.json')
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename, 'r') as handle:
            summary = json.load(handle)
        # older summaries hold float32 norms written as strings
        return {
            var: {name: float(norm) for name, norm in norms.items()}
            for var, norms in summary.items()
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


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


def read_cf_status_from_logs(step_work_dir: str) -> Optional[bool]:
    """Get CF check status from existing log markers.

    Returns
    -------
    Optional[bool]
        True if ``cf_check_passed.log`` exists, False if
        ``cf_check_failed.log`` exists, otherwise None.
    """
    if os.path.exists(os.path.join(step_work_dir, 'cf_check_passed.log')):
        return True
    if os.path.exists(os.path.join(step_work_dir, 'cf_check_failed.log')):
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


def _log_dependency_pickles(pickle_filenames, logger):
    """
    Record how large each dependency's pickle was.

    A dependency is unpickled whole into the process running the step, so a
    pickle that is large for what the step needs from it is memory held
    before the step has done anything.
    """
    for name, filename in pickle_filenames.items():
        size = format_bytes(os.path.getsize(filename))
        logger.info(f'loaded dependency {name} from {filename} ({size})')


def _run_pieces(step):
    """
    Run a step that hands out work, through the residents on its cores.

    Under ``polaris parallel`` the cores are the step's placement and the
    residents are the run's, both handed to the step by the scheduler.
    ``polaris serial`` gives a step neither, so the step's cores are laid
    out over the allocation and the run's residents started here, the first
    time a step needs them.  Either way the step sees the same thing.
    """
    residents = getattr(step, 'residents', None)
    placement = step.placement
    memory = getattr(step, 'reserved_memory', None)
    if residents is None and placement is None:
        residents, placement, memory = serial_resources(step)
    elif residents is None:
        raise RuntimeError(
            f'Step {step.path} hands out work, but no residents were started '
            f'to fork its pieces.'
        )
    elif placement is None:
        raise RuntimeError(
            f'Step {step.path} hands out work, but was given no cores to '
            f'hand it out to.'
        )
    # a summary left by an earlier run describes that run and not this one
    try:
        os.remove(os.path.join(step.work_dir, PIECES_SUMMARY))
    except OSError:
        pass
    with Pieces(step, slots_from(placement), residents, memory) as pieces:
        step.run_pieces(pieces)


def _log_sizing(step, step_resources, logger, when):
    """
    Record what the step is sized to and what its placement offers.

    A launch that asks for more tasks than its placement has cores for is
    rejected by the launcher, and the rejection names one node and two
    numbers.  Reconstructing which of the two sides moved from that alone
    is guesswork, so both are written down: what the step is sized to, and
    what the placement gives, per node and in total.
    """
    placement = step.placement
    if placement is None:
        shape = 'no placement; the whole allocation'
    else:
        per_node = [len(node_cores) for node_cores in placement.cores]
        shape = (
            f'{len(placement.nodes)} nodes, {placement.total_cores} cores, '
            f'per node {per_node}'
        )
    logger.info(
        f'sizing ({when}): ntasks={step.ntasks} '
        f'cpus_per_task={step.cpus_per_task} cores={step.cores} '
        f'min_tasks={step.min_tasks}; offered '
        f'{step_resources["cores"]} cores on '
        f'{step_resources["nodes"]} nodes; placement: {shape}'
    )
