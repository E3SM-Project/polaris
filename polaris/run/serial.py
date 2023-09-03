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


def run_tests(suite_name, quiet=False, is_test_case=False, steps_to_run=None,
              steps_to_skip=None):
    """
    Run the given test suite or test case

    Parameters
    ----------
    suite_name : str
        The name of the test suite

    quiet : bool, optional
        Whether step names are not included in the output as the test suite
        progresses

    is_test_case : bool
        Whether this is a test case instead of a full test suite

    steps_to_run : list of str, optional
        A list of the steps to run if this is a test case, not a full suite.
        The default behavior is to run the default steps unless they are in
        ``steps_to_skip``

    steps_to_skip : list of str, optional
        A list of steps not to run if this is a test case, not a full suite.
        Typically, these are steps to remove from the defaults
    """

    test_suite = unpickle_suite(suite_name)

    # get the config file for the first test case in the suite
    test_case = next(iter(test_suite['test_cases'].values()))
    config_filename = os.path.join(test_case.work_dir,
                                   test_case.config_filename)
    config = setup_config(config_filename)
    available_resources = get_available_parallel_resources(config)

    # start logging to stdout/stderr
    with LoggingContext(suite_name) as stdout_logger:

        os.environ['PYTHONUNBUFFERED'] = '1'

        if not is_test_case:
            try:
                os.makedirs('case_outputs')
            except OSError:
                pass

        failures = 0
        cwd = os.getcwd()
        suite_start = time.time()
        test_times = dict()
        success_strs = dict()
        for test_name in test_suite['test_cases']:
            stdout_logger.info(f'{test_name}')

            test_case = test_suite['test_cases'][test_name]

            if is_test_case:
                log_filename = None
                test_logger = stdout_logger
            else:
                test_prefix = test_case.path.replace('/', '_')
                log_filename = f'{cwd}/case_outputs/{test_prefix}.log'
                test_logger = None

            success_str, success, test_time = _log_and_run_test(
                test_case, stdout_logger, test_logger, quiet, log_filename,
                is_test_case, steps_to_run, steps_to_skip,
                available_resources)
            success_strs[test_name] = success_str
            if not success:
                failures += 1
            test_times[test_name] = test_time

        suite_time = time.time() - suite_start

        os.chdir(cwd)
        _log_test_runtimes(stdout_logger, test_times, success_strs, suite_time,
                           failures)


def run_single_step(step_is_subprocess=False):
    """
    Used by the framework to run a step when ``polaris serial`` gets called in
    the step's work directory

    Parameters
    ----------
    step_is_subprocess : bool, optional
        Whether the step is being run as a subprocess of a test case or suite
    """
    with open('step.pickle', 'rb') as handle:
        test_case, step = pickle.load(handle)
    test_case.steps_to_run = [step.name]
    test_case.new_step_log_file = False

    # This prevents infinite loop of subprocesses
    if step_is_subprocess:
        step.run_as_subprocess = False

    config = setup_config(step.config_filename)
    test_case.config = config
    available_resources = get_available_parallel_resources(config)
    set_cores_per_node(test_case.config, available_resources['cores_per_node'])

    mpas_tools.io.default_format = config.get('io', 'format')
    mpas_tools.io.default_engine = config.get('io', 'engine')

    # start logging to stdout/stderr
    test_name = step.path.replace('/', '_')
    with LoggingContext(name=test_name) as stdout_logger:
        test_case.logger = stdout_logger
        test_case.stdout_logger = None
        log_function_call(function=_run_test, logger=stdout_logger)
        stdout_logger.info('')
        _run_test(test_case, available_resources)

        if not step_is_subprocess:
            # only perform validation if the step is being run by a user on its
            # own
            stdout_logger.info('')
            log_method_call(method=test_case.validate, logger=stdout_logger)
            stdout_logger.info('')
            test_case.validate()


def main():
    parser = argparse.ArgumentParser(
        description='Run a test suite, test case or step',
        prog='polaris serial')
    parser.add_argument("suite", nargs='?',
                        help="The name of a test suite to run. Can exclude "
                        "or include the .pickle filename suffix.")
    parser.add_argument("--steps", dest="steps", nargs='+',
                        help="The steps of a test case to run.")
    parser.add_argument("--skip_steps", dest="skip_steps", nargs='+',
                        help="The steps of a test case not to run, see "
                             "steps_to_run in the config file for defaults.")
    parser.add_argument("-q", "--quiet", dest="quiet", action="store_true",
                        help="If set, step names are not included in the "
                             "output as the test suite progresses.  Has no "
                             "effect when running test cases or steps on "
                             "their own.")
    parser.add_argument("--step_is_subprocess", dest="step_is_subprocess",
                        action="store_true",
                        help="Used internally by polaris to indicate that "
                             "a step is being run as a subprocess.")
    args = parser.parse_args(sys.argv[2:])

    if args.suite is not None:
        # Running a specified suite from the base work directory
        run_tests(args.suite, quiet=args.quiet)
    elif os.path.exists('test_case.pickle'):
        # Running a test case inside of its work directory
        run_tests(suite_name='test_case', quiet=args.quiet, is_test_case=True,
                  steps_to_run=args.steps, steps_to_skip=args.skip_steps)
    elif os.path.exists('step.pickle'):
        # Running a step inside of its work directory
        run_single_step(args.step_is_subprocess)
    else:
        pickles = glob.glob('*.pickle')
        if len(pickles) == 1:
            # Running an unspecified suite from the base work directory
            suite = os.path.splitext(os.path.basename(pickles[0]))[0]
            run_tests(suite, quiet=args.quiet)
        elif len(pickles) == 0:
            raise OSError('No pickle files were found. Are you sure this is '
                          'a polaris suite, test-case or step work directory?')
        else:
            raise ValueError('More than one suite was found. Please specify '
                             'which to run: polaris serial <suite>')


def _update_steps_to_run(steps_to_run, steps_to_skip, config, steps):
    """
    Update the steps to run
    """
    if steps_to_run is None:
        steps_to_run = config.get('test_case',
                                  'steps_to_run').replace(',', ' ').split()

    for step in steps_to_run:
        if step not in steps:
            raise ValueError(
                f'A step "{step}" was requested but is not one of the steps '
                f'in this test case:'
                f'\n{list(steps)}')

    if steps_to_skip is not None:
        for step in steps_to_skip:
            if step not in steps:
                raise ValueError(
                    f'A step "{step}" was flagged not to run but is not one '
                    f'of the steps in this test case:'
                    f'\n{list(steps)}')

        steps_to_run = [step for step in steps_to_run if step not in
                        steps_to_skip]

    return steps_to_run


def _log_test_runtimes(stdout_logger, test_times, success_strs, suite_time,
                       failures):
    """
    Log the runtimes for the test case(s)
    """
    stdout_logger.info('Test Runtimes:')
    for test_name, test_time in test_times.items():
        test_time_str = str(timedelta(seconds=round(test_time)))
        stdout_logger.info(f'{test_time_str} '
                           f'{success_strs[test_name]} {test_name}')
    suite_time_str = str(timedelta(seconds=round(suite_time)))
    stdout_logger.info(f'Total runtime: {suite_time_str}')

    if failures == 0:
        stdout_logger.info('PASS: All passed successfully!')
    else:
        if failures == 1:
            message = '1 test'
        else:
            message = f'{failures} tests'
        stdout_logger.error(f'FAIL: {message} failed, see above.')
        sys.exit(1)


def _print_to_stdout(test_case, message):
    """
    Write out a message to stdout if we're not running a single step
    """
    if test_case.stdout_logger is not None:
        test_case.stdout_logger.info(message)
        if test_case.logger != test_case.stdout_logger:
            # also write it to the log file
            test_case.logger.info(message)


def _log_and_run_test(test_case, stdout_logger, test_logger, quiet,
                      log_filename, is_test_case, steps_to_run,
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

    test_name = test_case.path.replace('/', '_')
    with LoggingContext(test_name, logger=test_logger,
                        log_filename=log_filename) as test_logger:
        if quiet:
            # just log the step names and any failure messages to the
            # log file
            test_case.stdout_logger = test_logger
        else:
            # log steps to stdout
            test_case.stdout_logger = stdout_logger
        test_case.logger = test_logger
        test_case.log_filename = log_filename

        # If we are running a test case on its own, we want a log file per step
        # If we are running within a suite, we want a log file per test, with
        #   output from each of its steps
        test_case.new_step_log_file = is_test_case

        os.chdir(test_case.work_dir)

        config = setup_config(test_case.config_filename)
        test_case.config = config
        set_cores_per_node(test_case.config,
                           available_resources['cores_per_node'])

        mpas_tools.io.default_format = config.get('io', 'format')
        mpas_tools.io.default_engine = config.get('io', 'engine')

        test_case.steps_to_run = _update_steps_to_run(
            steps_to_run, steps_to_skip, config, test_case.steps)

        test_start = time.time()

        log_function_call(function=_run_test, logger=test_logger)
        test_logger.info('')
        test_list = ', '.join(test_case.steps_to_run)
        test_logger.info(f'Running steps: {test_list}')
        try:
            _run_test(test_case, available_resources)
            run_status = success_str
            test_pass = True
        except BaseException:
            run_status = error_str
            test_pass = False
            test_logger.exception('Exception raised while running '
                                  'the steps of the test case')

        if test_pass:
            test_logger.info('')
            log_method_call(method=test_case.validate,
                            logger=test_logger)
            test_logger.info('')
            try:
                test_case.validate()
            except BaseException:
                run_status = error_str
                test_pass = False
                test_logger.exception('Exception raised in the test '
                                      'case\'s validate() method')

        baseline_status = None
        internal_status = None
        if test_case.validation is not None:
            internal_pass = test_case.validation['internal_pass']
            baseline_pass = test_case.validation['baseline_pass']

            if internal_pass is not None:
                if internal_pass:
                    internal_status = pass_str
                else:
                    internal_status = fail_str
                    test_logger.error(
                        'Internal test case validation failed')
                    test_pass = False

            if baseline_pass is not None:
                if baseline_pass:
                    baseline_status = pass_str
                else:
                    baseline_status = fail_str
                    test_logger.error('Baseline validation failed')
                    test_pass = False

        status = f'  test execution:      {run_status}'
        if internal_status is not None:
            status = f'{status}\n' \
                     f'  test validation:     {internal_status}'
        if baseline_status is not None:
            status = f'{status}\n' \
                     f'  baseline comparison: {baseline_status}'

        if test_pass:
            stdout_logger.info(status)
            success_str = pass_str
            success = True
        else:
            stdout_logger.error(status)
            if not is_test_case:
                stdout_logger.error(f'  see: case_outputs/{test_name}.log')
            success_str = fail_str
            success = False

        test_time = time.time() - test_start

        test_time_str = str(timedelta(seconds=round(test_time)))
        stdout_logger.info(f'  test runtime:        '
                           f'{start_time_color}{test_time_str}{end}')

        return success_str, success, test_time


def _run_test(test_case, available_resources):
    """
    Run each step of the test case
    """
    start_time_color = '\033[94m'
    end = '\033[0m'

    logger = test_case.logger
    cwd = os.getcwd()
    for step_name in test_case.steps_to_run:
        step = test_case.steps[step_name]
        step_start = time.time()

        if step.cached:
            logger.info(f'  * Cached step: {step_name}')
            continue
        step.config = test_case.config
        if test_case.log_filename is not None:
            step_log_filename = test_case.log_filename
        else:
            step_log_filename = None

        _print_to_stdout(test_case, f'  * step: {step_name}')

        try:
            if step.run_as_subprocess:
                _run_step_as_subprocess(
                    test_case, step, test_case.new_step_log_file)
            else:
                _run_step(test_case, step, test_case.new_step_log_file,
                          available_resources, step_log_filename)
        except BaseException:
            _print_to_stdout(test_case, '      Failed')
            raise
        os.chdir(cwd)
        step_time = time.time() - step_start
        step_time_str = str(timedelta(seconds=round(step_time)))
        _print_to_stdout(test_case,
                         f'          runtime:     '
                         f'{start_time_color}{step_time_str}{end}')


def _run_step(test_case, step, new_log_file, available_resources,
              step_log_filename):
    """
    Run the requested step
    """
    logger = test_case.logger
    cwd = os.getcwd()

    missing_files = list()
    for input_file in step.inputs:
        if not os.path.exists(input_file):
            missing_files.append(input_file)

    if len(missing_files) > 0:
        raise OSError(
            f'input file(s) missing in step {step.name} of '
            f'{step.component.name}/{step.test_group.name}/'
            f'{step.test_case.subdir}: {missing_files}')

    load_dependencies(test_case, step)

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

    pickle_step_after_run(test_case, step)

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
            f'{step.component.name}/{step.test_group.name}/'
            f'{step.test_case.subdir}: {missing_files}')


def _run_step_as_subprocess(test_case, step, new_log_file):
    """
    Run the requested step as a subprocess
    """
    logger = test_case.logger
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
