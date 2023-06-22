import argparse
import sys
from typing import List

from polaris.io import imp_res
from polaris.setup import setup_cases


def setup_suite(component, suite_name, work_dir, config_file=None,
                machine=None, baseline_dir=None, component_path=None,
                copy_executable=False):
    """
    Set up a test suite

    Parameters
    ----------
    component : str
        The component ('ocean', 'landice', etc.) of the test suite

    suite_name : str
        The name of the test suite.  A file ``<suite_name>.txt`` must exist
        within the core's ``suites`` package that lists the paths of the tests
        in the suite

    config_file : str, optional
        Configuration file with custom options for setting up and running
        test cases

    machine : str, optional
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    work_dir : str, optional
        A directory that will serve as the base for creating test case
        directories

    baseline_dir : str, optional
        Location of baselines that can be compared to

    component_path : str, optional
        The relative or absolute path to the location where the model and
        default namelists have been built

    copy_executable : bool, optional
        Whether to copy the MPAS executable to the work directory
    """

    text = imp_res.files(f'polaris.{component}.suites').joinpath(
        f'{suite_name}.txt').read_text()

    tests, cached = _parse_suite(text)

    setup_cases(work_dir, tests, config_file=config_file, machine=machine,
                baseline_dir=baseline_dir, component_path=component_path,
                suite_name=suite_name, cached=cached,
                copy_executable=copy_executable)


def main():
    parser = argparse.ArgumentParser(
        description='Set up a regression test suite', prog='polaris suite')
    parser.add_argument("-c", "--component", dest="component",
                        help="The component for the test suite.",
                        metavar="COMPONENT", required=True)
    parser.add_argument("-t", "--test_suite", dest="test_suite",
                        help="Path to file containing a test suite to setup.",
                        metavar="SUITE", required=True)
    parser.add_argument("-f", "--config_file", dest="config_file",
                        help="Configuration file for test case setup.",
                        metavar="FILE")
    parser.add_argument("-m", "--machine", dest="machine",
                        help="The name of the machine for loading machine-"
                             "related config options.", metavar="MACH")
    parser.add_argument("-b", "--baseline_dir", dest="baseline_dir",
                        help="Location of baselines that can be compared to.",
                        metavar="PATH")
    parser.add_argument("-w", "--work_dir", dest="work_dir", required=True,
                        help="If set, script will setup the test suite in "
                        "work_dir rather in this script's location.",
                        metavar="PATH")
    parser.add_argument("-p", "--component_path", dest="component_path",
                        help="The path where the component executable and "
                             "default namelists have been built.",
                        metavar="PATH")
    parser.add_argument("--copy_executable", dest="copy_executable",
                        action="store_true",
                        help="If the model executable should be copied to the "
                             "work directory.")
    args = parser.parse_args(sys.argv[2:])

    setup_suite(component=args.component, suite_name=args.test_suite,
                work_dir=args.work_dir, config_file=args.config_file,
                machine=args.machine, baseline_dir=args.baseline_dir,
                component_path=args.component_path,
                copy_executable=args.copy_executable)


def _parse_suite(text):
    """ Parse the text of a file defining a test suite """

    tests: List[str] = list()
    cached: List[List[str]] = list()
    for test in text.split('\n'):
        test = test.strip()
        if len(test) == 0 or test.startswith('#'):
            # a blank line or comment
            continue

        if test == 'cached':
            cached[-1] = ['_all']
        elif test.startswith('cached:'):
            steps = test[len('cached:'):].strip().split(' ')
            cached[-1].extend(steps)
        else:
            tests.append(test)
            cached.append(list())

    return tests, cached
