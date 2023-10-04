import argparse
import glob
import os
import pickle
import sys
import time
from datetime import timedelta

import mpas_tools.io
from mpas_tools.logging import LoggingContext, check_call

from polaris import Task
from polaris.logging import log_function_call, log_method_call
from polaris.parallel import (
    get_available_parallel_resources,
    run_command,
    set_cores_per_node,
)
from polaris.run import (
    complete_step_run,
    load_dependencies,
    setup_config,
    unpickle_suite,
)

# ANSI fail text: https://stackoverflow.com/a/287944/7728169
start_fail = '\033[91m'
start_pass = '\033[92m'
start_time_color = '\033[94m'
end_color = '\033[0m'
pass_str = f'{start_pass}PASS{end_color}'
success_str = f'{start_pass}SUCCESS{end_color}'
fail_str = f'{start_fail}FAIL{end_color}'
error_str = f'{start_fail}ERROR{end_color}'


def run_tasks(suite_name, quiet=False, is_task=False, steps_to_run=None,
              steps_to_skip=None):
    """
    Run the given suite or task

    Parameters
    ----------
    suite_name : str
        The name of the suite

    quiet : bool, optional
        Whether step names are not included in the output as the suite
        progresses

    is_task : bool
        Whether this is a task instead of a full suite

    steps_to_run : list of str, optional
        A list of the steps to run if this is a task, not a full suite.
        The default behavior is to run the default steps unless they are in
        ``steps_to_skip``

    steps_to_skip : list of str, optional
        A list of steps not to run if this is a task, not a full suite.
        Typically, these are steps to remove from the defaults
    """

    suite = unpickle_suite(suite_name)

    # get the config file for the first task in the suite
    task = next(iter(suite['tasks'].values()))
    component = task.component
    config_filename = \
        f'{task.base_work_dir}/{component.name}/{component.name}.cfg'
    common_config = setup_config(config_filename)
    available_resources = get_available_parallel_resources(common_config)

    # start logging to stdout/stderr
    with LoggingContext(suite_name) as stdout_logger:

        os.environ['PYTHONUNBUFFERED'] = '1'

        if not is_task:
            try:
                os.makedirs('case_outputs')
            except OSError:
                pass

        failures = 0
        cwd = os.getcwd()
        suite_start = time.time()
        task_times = dict()
        result_strs = dict()
        for task_name in suite['tasks']:
            stdout_logger.info(f'{task_name}')

            task = suite['tasks'][task_name]

            if is_task:
                log_filename = None
                task_logger = stdout_logger
            else:
                task_prefix = task.path.replace('/', '_')
                log_filename = f'{cwd}/case_outputs/{task_prefix}.log'
                task_logger = None

            result_str, success, task_time = _log_and_run_task(
                task, stdout_logger, task_logger, quiet, log_filename,
                is_task, steps_to_run, steps_to_skip,
                available_resources)
            result_strs[task_name] = result_str
            if not success:
                failures += 1
            task_times[task_name] = task_time

        suite_time = time.time() - suite_start

        os.chdir(cwd)
        _log_task_runtimes(stdout_logger, task_times, result_strs, suite_time,
                           failures)


def run_single_step(step_is_subprocess=False, quiet=False):
    """
    Used by the framework to run a step when ``polaris serial`` gets called in
    the step's work directory

    Parameters
    ----------
    step_is_subprocess : bool, optional
        Whether the step is being run as a subprocess of a task or suite

    quiet : bool, optional
        Whether step names are not included in the output as the suite
        progresses
    """
    with open('step.pickle', 'rb') as handle:
        step = pickle.load(handle)
    task = Task(component=step.component, name='dummy_task')
    task.add_step(step)
    task.new_step_log_file = False

    # This prevents infinite loop of subprocesses
    if step_is_subprocess:
        step.run_as_subprocess = False

    config_filename = os.path.join(step.base_work_dir,
                                   step.component.name,
                                   step.config.filepath)
    config = setup_config(config_filename)
    task.config = config
    available_resources = get_available_parallel_resources(config)
    set_cores_per_node(task.config, available_resources['cores_per_node'])

    mpas_tools.io.default_format = config.get('io', 'format')
    mpas_tools.io.default_engine = config.get('io', 'engine')

    # start logging to stdout/stderr
    logger_name = step.path.replace('/', '_')
    with LoggingContext(name=logger_name) as stdout_logger:
        task.logger = stdout_logger
        if quiet:
            task.stdout_logger = None
        else:
            task.stdout_logger = stdout_logger
            log_function_call(function=_run_task, logger=stdout_logger)
            stdout_logger.info('')
            stdout_logger.info(f'Running step: {step.name}')
        _run_task(task, available_resources)


def main():
    parser = argparse.ArgumentParser(
        description='Run a suite, task or step',
        prog='polaris serial')
    parser.add_argument("suite", nargs='?',
                        help="The name of a suite to run. Can exclude "
                        "or include the .pickle filename suffix.")
    parser.add_argument("--steps", dest="steps", nargs='+',
                        help="The steps of a task to run.")
    parser.add_argument("--skip_steps", dest="skip_steps", nargs='+',
                        help="The steps of a task not to run, see "
                             "steps_to_run in the config file for defaults.")
    parser.add_argument("-q", "--quiet", dest="quiet", action="store_true",
                        help="If set, step names are not included in the "
                             "output as the suite progresses.  Has no "
                             "effect when running tasks or steps on "
                             "their own.")
    parser.add_argument("--step_is_subprocess", dest="step_is_subprocess",
                        action="store_true",
                        help="Used internally by polaris to indicate that "
                             "a step is being run as a subprocess.")
    args = parser.parse_args(sys.argv[2:])

    if args.suite is not None:
        # Running a specified suite from the base work directory
        run_tasks(args.suite, quiet=args.quiet)
    elif os.path.exists('task.pickle'):
        # Running a task inside of its work directory
        run_tasks(suite_name='task', quiet=args.quiet, is_task=True,
                  steps_to_run=args.steps, steps_to_skip=args.skip_steps)
    elif os.path.exists('step.pickle'):
        # Running a step inside of its work directory
        run_single_step(step_is_subprocess=args.step_is_subprocess,
                        quiet=args.quiet)
    else:
        pickles = glob.glob('*.pickle')
        if len(pickles) == 1:
            # Running an unspecified suite from the base work directory
            suite = os.path.splitext(os.path.basename(pickles[0]))[0]
            run_tasks(suite, quiet=args.quiet)
        elif len(pickles) == 0:
            raise OSError('No pickle files were found. Are you sure this is '
                          'a polaris suite, task or step work directory?')
        else:
            raise ValueError('More than one suite was found. Please specify '
                             'which to run: polaris serial <suite>')


def _update_steps_to_run(task_name, steps_to_run, steps_to_skip, config,
                         steps):
    """
    Update the steps to run
    """
    if steps_to_run is None:
        step_str = config.get(task_name, 'steps_to_run').replace(',', ' ')
        steps_to_run = step_str.split()

    for step in steps_to_run:
        if step not in steps:
            raise ValueError(
                f'A step "{step}" was requested but is not one of the steps '
                f'in this task:'
                f'\n{list(steps)}')

    if steps_to_skip is not None:
        for step in steps_to_skip:
            if step not in steps:
                raise ValueError(
                    f'A step "{step}" was flagged not to run but is not one '
                    f'of the steps in this task:'
                    f'\n{list(steps)}')

        steps_to_run = [step for step in steps_to_run if step not in
                        steps_to_skip]

    return steps_to_run


def _log_task_runtimes(stdout_logger, task_times, result_strs, suite_time,
                       failures):
    """
    Log the runtimes for the task(s)
    """
    stdout_logger.info('Task Runtimes:')
    for task_name, task_time in task_times.items():
        task_time_str = str(timedelta(seconds=round(task_time)))
        stdout_logger.info(f'{task_time_str} '
                           f'{result_strs[task_name]} {task_name}')
    suite_time_str = str(timedelta(seconds=round(suite_time)))
    stdout_logger.info(f'Total runtime: {suite_time_str}')

    if failures == 0:
        stdout_logger.info('PASS: All passed successfully!')
    else:
        if failures == 1:
            message = '1 task'
        else:
            message = f'{failures} tasks'
        stdout_logger.error(f'FAIL: {message} failed, see above.')
        sys.exit(1)


def _print_to_stdout(task, message):
    """
    Write out a message to stdout if we're not running a single step
    """
    if task.stdout_logger is not None:
        task.stdout_logger.info(message)
        if task.logger != task.stdout_logger:
            # also write it to the log file
            task.logger.info(message)


def _log_and_run_task(task, stdout_logger, task_logger, quiet,
                      log_filename, is_task, steps_to_run,
                      steps_to_skip, available_resources):

    task_name = task.path.replace('/', '_')
    with LoggingContext(task_name, logger=task_logger,
                        log_filename=log_filename) as task_logger:
        if quiet:
            # just log the step names and any failure messages to the
            # log file
            task.stdout_logger = task_logger
        else:
            # log steps to stdout
            task.stdout_logger = stdout_logger
        task.logger = task_logger
        task.log_filename = log_filename

        # If we are running a task on its own, we want a log file per step
        # If we are running within a suite, we want a log file per task, with
        #   output from each of its steps
        task.new_step_log_file = is_task

        os.chdir(task.work_dir)

        config_filename = os.path.join(task.base_work_dir,
                                       task.component.name,
                                       task.config.filepath)
        config = setup_config(config_filename)
        task.config = config
        set_cores_per_node(task.config,
                           available_resources['cores_per_node'])

        mpas_tools.io.default_format = config.get('io', 'format')
        mpas_tools.io.default_engine = config.get('io', 'engine')

        task.steps_to_run = _update_steps_to_run(
            task.name, steps_to_run, steps_to_skip, config, task.steps)

        task_start = time.time()

        log_function_call(function=_run_task, logger=task_logger)
        task_logger.info('')
        task_list = ', '.join(task.steps_to_run)
        task_logger.info(f'Running steps: {task_list}')
        try:
            baselines_passed = _run_task(task, available_resources)
            run_status = success_str
            task_pass = True
        except Exception:
            run_status = error_str
            task_pass = False
            task_logger.exception('Exception raised while running '
                                  'the steps of the task')

        status = f'  task execution:   {run_status}'
        if task_pass:
            stdout_logger.info(status)
            if baselines_passed:
                baseline_str = pass_str
                result_str = pass_str
                success = True
            else:
                baseline_str = fail_str
                result_str = fail_str
                success = False
            status = f'  baseline comp.:   {baseline_str}'
            stdout_logger.info(status)
        else:
            stdout_logger.error(status)
            if not is_task:
                stdout_logger.error(f'  see: case_outputs/{task_name}.log')
            result_str = fail_str
            success = False

        task_time = time.time() - task_start

        task_time_str = str(timedelta(seconds=round(task_time)))
        stdout_logger.info(f'  task runtime:     '
                           f'{start_time_color}{task_time_str}{end_color}')

        return result_str, success, task_time


def _run_task(task, available_resources):
    """
    Run each step of the task
    """
    logger = task.logger
    cwd = os.getcwd()
    baselines_passed = True
    for step_name in task.steps_to_run:
        step = task.steps[step_name]
        complete_filename = os.path.join(step.work_dir,
                                         'polaris_step_complete.log')

        _print_to_stdout(task, f'  * step: {step_name}')

        if os.path.exists(complete_filename):
            _print_to_stdout(task, '          already completed')
            continue
        if step.cached:
            _print_to_stdout(task, '          cached')
            continue

        step_start = time.time()

        config_filename = os.path.join(step.base_work_dir,
                                       step.component.name,
                                       step.config.filepath)

        step.config = setup_config(config_filename)
        if task.log_filename is not None:
            step_log_filename = task.log_filename
        else:
            step_log_filename = None

        try:
            if step.run_as_subprocess:
                _run_step_as_subprocess(
                    logger, step, task.new_step_log_file)
            else:
                _run_step(task, step, task.new_step_log_file,
                          available_resources, step_log_filename)
        except Exception:
            _print_to_stdout(task,
                             f'          execution:        {error_str}')
            raise
        _print_to_stdout(task,
                         f'          execution:        {success_str}')
        os.chdir(cwd)
        step_time = time.time() - step_start
        step_time_str = str(timedelta(seconds=round(step_time)))

        compared, status = step.validate_baselines()
        if compared:
            if status:
                baseline_str = pass_str
            else:
                baseline_str = fail_str
            _print_to_stdout(task,
                             f'          baseline comp.:   {baseline_str}')
            if not status:
                baselines_passed = False

        _print_to_stdout(task,
                         f'          runtime:          '
                         f'{start_time_color}{step_time_str}{end_color}')

    return baselines_passed


def _run_step(task, step, new_log_file, available_resources,
              step_log_filename):
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
            f'{step.component.name}/{step.subdir}: {missing_files}')

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

    with LoggingContext(name=logger_name, logger=step_logger,
                        log_filename=new_log_filename) as step_logger:
        step.logger = step_logger
        os.chdir(step.work_dir)

        step_logger.info('')
        log_method_call(method=step.constrain_resources, logger=step_logger)
        step_logger.info('')
        step.constrain_resources(available_resources)

        # runtime_setup() will perform small tasks that require knowing the
        # resources of the task before the step runs (such as creating
        # graph partitions)
        step_logger.info('')
        log_method_call(method=step.runtime_setup, logger=step_logger)
        step_logger.info('')
        step.runtime_setup()

        if step.args is not None:
            step_logger.info('\nBypassing step\'s run() method and running '
                             'with command line args\n')
            log_function_call(function=run_command, logger=step_logger)
            step_logger.info('')
            run_command(step.args, step.cpus_per_task, step.ntasks,
                        step.openmp_threads, step.config, step.logger)
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
            f'{step.component.name}/{step.subdir}: {missing_files}')


def _run_step_as_subprocess(logger, step, new_log_file):
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

    with LoggingContext(name=logger_name, logger=step_logger,
                        log_filename=log_filename) as step_logger:

        os.chdir(step.work_dir)
        step_args = ['polaris', 'serial', '--step_is_subprocess']
        check_call(step_args, step_logger)
