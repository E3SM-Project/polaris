import argparse
import glob
import os
import pickle
import sys
import time
from datetime import timedelta

import mpas_tools.io
from mpas_tools.logging import LoggingContext, check_call

from polaris.logging import log_function_call, log_method_call
from polaris.parallel import (
    get_available_parallel_resources,
    run_command,
    set_cores_per_node,
)
from polaris.run import (
    load_dependencies,
    pickle_step_after_run,
    setup_config,
    unpickle_suite,
)


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
    config_filename = os.path.join(task.work_dir,
                                   task.config_filename)
    config = setup_config(config_filename)
    available_resources = get_available_parallel_resources(config)

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
        success_strs = dict()
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

            success_str, success, task_time = _log_and_run_task(
                task, stdout_logger, task_logger, quiet, log_filename,
                is_task, steps_to_run, steps_to_skip,
                available_resources)
            success_strs[task_name] = success_str
            if not success:
                failures += 1
            task_times[task_name] = task_time

        suite_time = time.time() - suite_start

        os.chdir(cwd)
        _log_task_runtimes(stdout_logger, task_times, success_strs, suite_time,
                           failures)


def run_single_step(step_is_subprocess=False):
    """
    Used by the framework to run a step when ``polaris serial`` gets called in
    the step's work directory

    Parameters
    ----------
    step_is_subprocess : bool, optional
        Whether the step is being run as a subprocess of a task or suite
    """
    with open('step.pickle', 'rb') as handle:
        task, step = pickle.load(handle)
    task.steps_to_run = [step.name]
    task.new_step_log_file = False

    # This prevents infinite loop of subprocesses
    if step_is_subprocess:
        step.run_as_subprocess = False

    config = setup_config(step.config_filename)
    task.config = config
    available_resources = get_available_parallel_resources(config)
    set_cores_per_node(task.config, available_resources['cores_per_node'])

    mpas_tools.io.default_format = config.get('io', 'format')
    mpas_tools.io.default_engine = config.get('io', 'engine')

    # start logging to stdout/stderr
    task_name = step.path.replace('/', '_')
    with LoggingContext(name=task_name) as stdout_logger:
        task.logger = stdout_logger
        task.stdout_logger = None
        log_function_call(function=_run_task, logger=stdout_logger)
        stdout_logger.info('')
        _run_task(task, available_resources)

        if not step_is_subprocess:
            # only perform validation if the step is being run by a user on its
            # own
            stdout_logger.info('')
            log_method_call(method=task.validate, logger=stdout_logger)
            stdout_logger.info('')
            task.validate()


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
        run_single_step(args.step_is_subprocess)
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


def _update_steps_to_run(steps_to_run, steps_to_skip, config, steps):
    """
    Update the steps to run
    """
    if steps_to_run is None:
        steps_to_run = config.get('task',
                                  'steps_to_run').replace(',', ' ').split()

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


def _log_task_runtimes(stdout_logger, task_times, success_strs, suite_time,
                       failures):
    """
    Log the runtimes for the task(s)
    """
    stdout_logger.info('Task Runtimes:')
    for task_name, task_time in task_times.items():
        task_time_str = str(timedelta(seconds=round(task_time)))
        stdout_logger.info(f'{task_time_str} '
                           f'{success_strs[task_name]} {task_name}')
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
    # ANSI fail text: https://stackoverflow.com/a/287944/7728169
    start_fail = '\033[91m'
    start_pass = '\033[92m'
    start_time_color = '\033[94m'
    end = '\033[0m'
    pass_str = f'{start_pass}PASS{end}'
    success_str = f'{start_pass}SUCCESS{end}'
    fail_str = f'{start_fail}FAIL{end}'
    error_str = f'{start_fail}ERROR{end}'

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

        config = setup_config(task.config_filename)
        task.config = config
        set_cores_per_node(task.config,
                           available_resources['cores_per_node'])

        mpas_tools.io.default_format = config.get('io', 'format')
        mpas_tools.io.default_engine = config.get('io', 'engine')

        task.steps_to_run = _update_steps_to_run(
            steps_to_run, steps_to_skip, config, task.steps)

        task_start = time.time()

        log_function_call(function=_run_task, logger=task_logger)
        task_logger.info('')
        task_list = ', '.join(task.steps_to_run)
        task_logger.info(f'Running steps: {task_list}')
        try:
            _run_task(task, available_resources)
            run_status = success_str
            task_pass = True
        except BaseException:
            run_status = error_str
            task_pass = False
            task_logger.exception('Exception raised while running '
                                  'the steps of the task')

        if task_pass:
            task_logger.info('')
            log_method_call(method=task.validate,
                            logger=task_logger)
            task_logger.info('')
            try:
                task.validate()
            except BaseException:
                run_status = error_str
                task_pass = False
                task_logger.exception('Exception raised in the task\'s '
                                      'validate() method')

        baseline_status = None
        internal_status = None
        if task.validation is not None:
            internal_pass = task.validation['internal_pass']
            baseline_pass = task.validation['baseline_pass']

            if internal_pass is not None:
                if internal_pass:
                    internal_status = pass_str
                else:
                    internal_status = fail_str
                    task_logger.error(
                        'Internal task validation failed')
                    task_pass = False

            if baseline_pass is not None:
                if baseline_pass:
                    baseline_status = pass_str
                else:
                    baseline_status = fail_str
                    task_logger.error('Baseline validation failed')
                    task_pass = False

        status = f'  task execution:      {run_status}'
        if internal_status is not None:
            status = f'{status}\n' \
                     f'  task validation:     {internal_status}'
        if baseline_status is not None:
            status = f'{status}\n' \
                     f'  baseline comparison: {baseline_status}'

        if task_pass:
            stdout_logger.info(status)
            success_str = pass_str
            success = True
        else:
            stdout_logger.error(status)
            if not is_task:
                stdout_logger.error(f'  see: case_outputs/{task_name}.log')
            success_str = fail_str
            success = False

        task_time = time.time() - task_start

        task_time_str = str(timedelta(seconds=round(task_time)))
        stdout_logger.info(f'  task runtime:        '
                           f'{start_time_color}{task_time_str}{end}')

        return success_str, success, task_time


def _run_task(task, available_resources):
    """
    Run each step of the task
    """
    start_time_color = '\033[94m'
    end = '\033[0m'

    logger = task.logger
    cwd = os.getcwd()
    for step_name in task.steps_to_run:
        step = task.steps[step_name]
        step_start = time.time()

        if step.cached:
            logger.info(f'  * Cached step: {step_name}')
            continue
        step.config = task.config
        if task.log_filename is not None:
            step_log_filename = task.log_filename
        else:
            step_log_filename = None

        _print_to_stdout(task, f'  * step: {step_name}')

        try:
            if step.run_as_subprocess:
                _run_step_as_subprocess(
                    task, step, task.new_step_log_file)
            else:
                _run_step(task, step, task.new_step_log_file,
                          available_resources, step_log_filename)
        except BaseException:
            _print_to_stdout(task, '      Failed')
            raise
        os.chdir(cwd)
        step_time = time.time() - step_start
        step_time_str = str(timedelta(seconds=round(step_time)))
        _print_to_stdout(task,
                         f'          runtime:     '
                         f'{start_time_color}{step_time_str}{end}')


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
            f'input file(s) missing in step {step.name} of '
            f'{step.component.name}/{step.task.subdir}: {missing_files}')

    load_dependencies(task, step)

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

    pickle_step_after_run(task, step)

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
            f'output file(s) missing in step {step.name} of '
            f'{step.component.name}/{step.task.subdir}: {missing_files}')


def _run_step_as_subprocess(task, step, new_log_file):
    """
    Run the requested step as a subprocess
    """
    logger = task.logger
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
