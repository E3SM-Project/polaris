import argparse
import os
import pickle
import sys
import warnings
from typing import Dict, List

from mache import discover_machine

from polaris import provenance
from polaris.components import get_components
from polaris.config import PolarisConfigParser
from polaris.io import symlink
from polaris.job import write_job_script
from polaris.testcase import TestCase


def setup_cases(work_dir, tests=None, numbers=None, config_file=None,
                machine=None, baseline_dir=None, component_path=None,
                suite_name='custom', cached=None, copy_executable=False):
    """
    Set up one or more test cases

    Parameters
    ----------
    work_dir : str
        A directory that will serve as the base for creating testcase
        directories

    tests : list of str, optional
        Relative paths for a test cases to set up

    numbers : list of str, optional
        Case numbers to setup, as listed from ``polaris list``, optionally with
        a suffix ``c`` to indicate that all steps in that test case should be
        cached

    config_file : {str, None}, optional
        Configuration file with custom options for setting up and running test
        cases

    machine : str, optional
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    baseline_dir : str, optional
        Location of baselines that can be compared to

    component_path : str, optional
        The relative or absolute path to the location where the model and
        default namelists have been built

    suite_name : str, optional
        The name of the test suite if tests are being set up through a test
        suite or ``'custom'`` if not

    cached : list of list of str, optional
        For each test in ``tests``, which steps (if any) should be cached,
        or a list with "_all" as the first entry if all steps in the test case
        should be cached

    copy_executable : bool, optional
        Whether to copy the model executable to the work directory

    Returns
    -------
    test_cases : dict of polaris.TestCase
        A dictionary of test cases, with the relative path in the work
        directory as keys
    """
    machine = __get_machine_and_check_params(machine, config_file, tests,
                                             numbers, cached)

    if work_dir is None:
        print('Warning: no base work directory was provided so setting up in '
              'the current directory.')
        work_dir = os.getcwd()
    work_dir = os.path.abspath(work_dir)

    components = get_components()

    all_test_cases = dict()
    for component in components:
        for test_group in component.test_groups.values():
            for test_case in test_group.test_cases.values():
                all_test_cases[test_case.path] = test_case

    test_cases: Dict[str, TestCase] = dict()
    cached_steps: Dict[str, List[str]] = dict()
    _add_test_cases_by_number(numbers, all_test_cases, test_cases,
                              cached_steps)
    _add_test_cases_by_name(tests, all_test_cases, cached, test_cases,
                            cached_steps)

    # get the component of the first test case.  We'll assume all tests are
    # for this core
    first_path = next(iter(test_cases))
    component = test_cases[first_path].component

    basic_config = _get_basic_config(config_file, machine, component_path,
                                     component)

    provenance.write(work_dir, test_cases, config=basic_config)

    print('Setting up test cases:')
    for path, test_case in test_cases.items():
        setup_case(path, test_case, config_file, machine, work_dir,
                   baseline_dir, component_path,
                   cached_steps=cached_steps[path],
                   copy_executable=copy_executable)

    test_suite = {'name': suite_name,
                  'test_cases': test_cases,
                  'work_dir': work_dir}

    # pickle the test or step dictionary for use at runtime
    pickle_file = os.path.join(test_suite['work_dir'],
                               f'{suite_name}.pickle')
    with open(pickle_file, 'wb') as handle:
        pickle.dump(test_suite, handle, protocol=pickle.HIGHEST_PROTOCOL)

    if 'LOAD_POLARIS_ENV' in os.environ:
        script_filename = os.environ['LOAD_POLARIS_ENV']
        # make a symlink to the script for loading the polaris conda env.
        symlink(script_filename, os.path.join(work_dir, 'load_polaris_env.sh'))

    max_cores, max_of_min_cores = _get_required_cores(test_cases)

    print(f'target cores: {max_cores}')
    print(f'minimum cores: {max_of_min_cores}')

    if machine is not None:
        write_job_script(basic_config, machine, max_cores, max_of_min_cores,
                         work_dir, suite=suite_name)

    return test_cases


def setup_case(path, test_case, config_file, machine, work_dir, baseline_dir,
               component_path, cached_steps, copy_executable):
    """
    Set up one or more test cases

    Parameters
    ----------
    path : str
        Relative path for a test cases to set up

    test_case : polaris.TestCase
        A test case to set up

    config_file : str
        Configuration file with custom options for setting up and running test
        cases

    machine : str
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    work_dir : str
        A directory that will serve as the base for creating case directories

    baseline_dir : str
        Location of baselines that can be compared to

    component_path : str
        The relative or absolute path to the location where the model and
        default namelists have been built

    cached_steps : list of str
        Which steps (if any) should be cached.  If all steps should be cached,
         the first entry is "_all"

    copy_executable : bool, optional
        Whether to copy the model executable to the work directory
    """

    print(f'  {path}')

    component_name = test_case.component.name
    config = _get_basic_config(config_file, machine, component_path,
                               test_case.component)

    # add the config options for the test group (if defined)
    test_group = test_case.test_group.name
    config.add_from_package(f'polaris.{component_name}.tests.{test_group}',
                            f'{test_group}.cfg', exception=False)

    if copy_executable:
        config.set('setup', 'copy_executable', 'True')

    # add the config options for the test case (if defined)
    config.add_from_package(test_case.__module__,
                            f'{test_case.name}.cfg', exception=False)

    if 'POLARIS_BRANCH' in os.environ:
        polaris_branch = os.environ['POLARIS_BRANCH']
        config.set('paths', 'polaris_branch', polaris_branch)
    else:
        config.set('paths', 'polaris_branch', os.getcwd())

    test_case_dir = os.path.join(work_dir, path)
    try:
        os.makedirs(test_case_dir)
    except OSError:
        pass
    test_case.work_dir = test_case_dir
    test_case.base_work_dir = work_dir

    # add config options specific to the test case
    test_case.config = config
    test_case.configure()

    # add the baseline directory for this test case
    if baseline_dir is not None:
        test_case.baseline_dir = os.path.join(baseline_dir, path)

    # set the component_path path from the command line if provided
    if component_path is not None:
        component_path = os.path.abspath(component_path)
        config.set('paths', 'component_path', component_path, user=True)

    config.set('test_case', 'steps_to_run', ' '.join(test_case.steps_to_run))

    # write out the config file
    test_case_config = f'{test_case.name}.cfg'
    test_case.config_filename = test_case_config
    with open(os.path.join(test_case_dir, test_case_config), 'w') as f:
        config.write(f)

    if len(cached_steps) > 0 and cached_steps[0] == '_all':
        cached_steps = list(test_case.steps.keys())
    if len(cached_steps) > 0:
        print_steps = ' '.join(cached_steps)
        print(f'    steps with cached outputs: {print_steps}')
    for step_name in cached_steps:
        test_case.steps[step_name].cached = True

    # iterate over steps
    for step in test_case.steps.values():
        # make the step directory if it doesn't exist
        step_dir = os.path.join(work_dir, step.path)
        try:
            os.makedirs(step_dir)
        except OSError:
            pass

        symlink(os.path.join(test_case_dir, test_case_config),
                os.path.join(step_dir, test_case_config))

        step.work_dir = step_dir
        step.base_work_dir = work_dir
        step.config_filename = test_case_config
        step.config = config

        # set up the step
        step.setup()

        # process input, output, namelist and streams files
        step.process_inputs_and_outputs()

    # wait until we've set up all the steps before pickling because steps may
    # need other steps to be set up
    for step in test_case.steps.values():

        # pickle the test case and step for use at runtime
        pickle_filename = os.path.join(step.work_dir, 'step.pickle')
        with open(pickle_filename, 'wb') as handle:
            pickle.dump((test_case, step), handle,
                        protocol=pickle.HIGHEST_PROTOCOL)

    # pickle the test case and step for use at runtime
    pickle_filename = os.path.join(test_case.work_dir, 'test_case.pickle')
    with open(pickle_filename, 'wb') as handle:
        test_suite = {'name': 'test_case',
                      'test_cases': {test_case.path: test_case},
                      'work_dir': test_case.work_dir}
        pickle.dump(test_suite, handle, protocol=pickle.HIGHEST_PROTOCOL)

    if 'LOAD_POLARIS_ENV' in os.environ:
        script_filename = os.environ['LOAD_POLARIS_ENV']
        # make a symlink to the script for loading the polaris conda env.
        symlink(script_filename, os.path.join(test_case_dir,
                                              'load_polaris_env.sh'))

    if machine is not None:
        max_cores, max_of_min_cores = _get_required_cores({path: test_case})
        write_job_script(config, machine, max_cores, max_of_min_cores,
                         test_case_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Set up one or more test cases', prog='polaris setup')
    parser.add_argument("-t", "--test", dest="test",
                        help="Relative path for a test case to set up",
                        metavar="PATH")
    parser.add_argument("-n", "--case_number", nargs='+', dest="case_num",
                        type=str,
                        help="Case number(s) to setup, as listed from "
                             "'polaris list'. Can be a space-separated"
                             "list of case numbers.  A suffix 'c' indicates"
                             "that all steps in the test should use cached"
                             "outputs.", metavar="NUM")
    parser.add_argument("-f", "--config_file", dest="config_file",
                        help="Configuration file for test case setup",
                        metavar="FILE")
    parser.add_argument("-m", "--machine", dest="machine",
                        help="The name of the machine for loading machine-"
                             "related config options", metavar="MACH")
    parser.add_argument("-w", "--work_dir", dest="work_dir", required=True,
                        help="A base directory for setting up test cases.",
                        metavar="PATH")
    parser.add_argument("-b", "--baseline_dir", dest="baseline_dir",
                        help="Location of baselines that can be compared to",
                        metavar="PATH")
    parser.add_argument("-p", "--component_path", dest="component_path",
                        help="The path where the component executable and "
                             "default namelists have been built.",
                        metavar="PATH")
    parser.add_argument("--suite_name", dest="suite_name", default="custom",
                        help="The name to use for the 'custom' test suite"
                             "containing all setup test cases.",
                        metavar="SUITE")
    parser.add_argument("--cached", dest="cached", nargs='+',
                        help="A list of steps in the test case supplied with"
                             "--test that should use cached outputs, or "
                             "'_all' if all steps should be cached",
                        metavar="STEP")
    parser.add_argument("--copy_executable", dest="copy_executable",
                        action="store_true",
                        help="If the model executable should be copied to the "
                             "work directory")

    args = parser.parse_args(sys.argv[2:])
    cached = None
    if args.test is None:
        tests = None
    else:
        tests = [args.test]
        if args.cached is not None:
            cached = [args.cached]
    setup_cases(tests=tests, numbers=args.case_num,
                config_file=args.config_file, machine=args.machine,
                work_dir=args.work_dir, baseline_dir=args.baseline_dir,
                component_path=args.component_path, suite_name=args.suite_name,
                cached=cached, copy_executable=args.copy_executable)


def _get_required_cores(test_cases):
    """ Get the maximum number of target cores and the max of min cores """

    max_cores = 0
    max_of_min_cores = 0
    for test_case in test_cases.values():
        for step_name in test_case.steps_to_run:
            step = test_case.steps[step_name]
            if step.ntasks is None:
                raise ValueError(
                    f'The number of tasks (ntasks) was never set for '
                    f'{test_case.path} step {step_name}')
            if step.cpus_per_task is None:
                raise ValueError(
                    f'The number of CPUs per task (cpus_per_task) was never '
                    f'set for {test_case.path} step {step_name}')
            cores = step.cpus_per_task * step.ntasks
            min_cores = step.min_cpus_per_task * step.min_tasks
            max_cores = max(max_cores, cores)
            max_of_min_cores = max(max_of_min_cores, min_cores)

    return max_cores, max_of_min_cores


def __get_machine_and_check_params(machine, config_file, tests, numbers,
                                   cached):
    if machine is None and 'POLARIS_MACHINE' in os.environ:
        machine = os.environ['POLARIS_MACHINE']

    if machine is None:
        machine = discover_machine()

    if config_file is None and machine is None:
        raise ValueError('At least one of config_file and machine is needed.')

    if config_file is not None and not os.path.exists(config_file):
        raise FileNotFoundError(
            f'The user config file wasn\'t found: {config_file}')

    if tests is None and numbers is None:
        raise ValueError('At least one of tests or numbers is needed.')

    if cached is not None:
        if tests is None:
            warnings.warn('Ignoring "cached" argument because "tests" was '
                          'not provided')
        elif len(cached) != len(tests):
            raise ValueError('A list of cached steps must be provided for '
                             'each test in "tests"')

    return machine


def _get_basic_config(config_file, machine, component_path, component):
    """
    Get a base config parser for the machine and component but not a specific
    test
    """
    config = PolarisConfigParser()

    if config_file is not None:
        config.add_user_config(config_file)

    # start with default polaris config options
    config.add_from_package('polaris', 'default.cfg')

    # add the E3SM config options from mache
    if machine is not None:
        config.add_from_package('mache.machines', f'{machine}.cfg')

    # add the polaris machine config file
    if machine is None:
        machine = 'default'
    config.add_from_package('polaris.machines', f'{machine}.cfg')

    if 'POLARIS_BRANCH' in os.environ:
        polaris_branch = os.environ['POLARIS_BRANCH']
        config.set('paths', 'polaris_branch', polaris_branch)
    else:
        config.set('paths', 'polaris_branch', os.getcwd())

    # add the config options for the component
    config.add_from_package(f'polaris.{component.name}',
                            f'{component.name}.cfg')

    component.configure(config)

    # set the component_path path from the command line if provided
    if component_path is not None:
        component_path = os.path.abspath(component_path)
        config.set('paths', 'component_path', component_path, user=True)

    return config


def _add_test_cases_by_number(numbers, all_test_cases, test_cases,
                              cached_steps):
    if numbers is not None:
        keys = list(all_test_cases)
        for number in numbers:
            cache_all = False
            if number.endswith('c'):
                cache_all = True
                number = int(number[:-1])
            else:
                number = int(number)

            if number >= len(keys):
                raise ValueError(f'test number {number} is out of range.  '
                                 f'There are only {len(keys)} tests.')
            path = keys[number]
            if cache_all:
                cached_steps[path] = ['_all']
            else:
                cached_steps[path] = list()
            test_cases[path] = all_test_cases[path]


def _add_test_cases_by_name(tests, all_test_cases, cached, test_cases,
                            cached_steps):
    if tests is not None:
        for index, path in enumerate(tests):
            if path not in all_test_cases:
                raise ValueError(f'Test case with path {path} is not in '
                                 f'test_cases')
            if cached is not None:
                cached_steps[path] = cached[index]
            else:
                cached_steps[path] = list()
            test_cases[path] = all_test_cases[path]
