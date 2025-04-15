import argparse
import importlib.resources as imp_res
import sys
from typing import List

from polaris.setup import setup_tasks


def setup_suite(
    component,
    suite_name,
    work_dir,
    config_file=None,
    machine=None,
    baseline_dir=None,
    component_path=None,
    copy_executable=False,
    clean=False,
    model=None,
):
    """
    Set up a suite of tasks

    Parameters
    ----------
    component : str
        The component ('ocean', 'landice', etc.) of the suite

    suite_name : str
        The name of the suite.  A file ``<suite_name>.txt`` must exist
        within the core's ``suites`` package that lists the paths of the tasks
        in the suite

    config_file : str, optional
        Configuration file with custom options for setting up and running
        tasks

    machine : str, optional
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    work_dir : str, optional
        A directory that will serve as the base for creating task
        directories

    baseline_dir : str, optional
        Location of baselines that can be compared to

    component_path : str, optional
        The relative or absolute path to the location where the model and
        default namelists have been built

    copy_executable : bool, optional
        Whether to copy the MPAS executable to the work directory

    clean : bool, optional
        Whether to delete the contents of the base work directory before
        setting up the suite

    model : str, optional
        The model to run
    """

    text = (
        imp_res.files(f'polaris.suites.{component}')
        .joinpath(f'{suite_name}.txt')
        .read_text()
    )

    tasks, cached = _parse_suite(text)

    setup_tasks(
        work_dir,
        tasks,
        config_file=config_file,
        machine=machine,
        baseline_dir=baseline_dir,
        component_path=component_path,
        suite_name=suite_name,
        cached=cached,
        copy_executable=copy_executable,
        clean=clean,
        model=model,
    )


def main():
    parser = argparse.ArgumentParser(
        description='Set up a regression suite', prog='polaris suite'
    )
    parser.add_argument(
        '-c',
        '--component',
        dest='component',
        help='The component for the suite.',
        metavar='COMPONENT',
        required=True,
    )
    parser.add_argument(
        '-t',
        '--task_suite',
        dest='task_suite',
        help='Path to file containing a suite to setup.',
        metavar='SUITE',
        required=True,
    )
    parser.add_argument(
        '-f',
        '--config_file',
        dest='config_file',
        help='Configuration file for task setup.',
        metavar='FILE',
    )
    parser.add_argument(
        '-m',
        '--machine',
        dest='machine',
        help='The name of the machine for loading machine-'
        'related config options.',
        metavar='MACH',
    )
    parser.add_argument(
        '-b',
        '--baseline_dir',
        dest='baseline_dir',
        help='Location of baselines that can be compared to.',
        metavar='PATH',
    )
    parser.add_argument(
        '-w',
        '--work_dir',
        dest='work_dir',
        required=True,
        help='If set, script will setup the suite in '
        "work_dir rather in this script's location.",
        metavar='PATH',
    )
    parser.add_argument(
        '-p',
        '--component_path',
        dest='component_path',
        help='The path where the component executable and '
        'default namelists have been built.',
        metavar='PATH',
    )
    parser.add_argument(
        '--copy_executable',
        dest='copy_executable',
        action='store_true',
        help='If the model executable should be copied to the work directory.',
    )
    parser.add_argument(
        '--clean',
        dest='clean',
        action='store_true',
        help='If the base work directory should be deleted '
        'before setting up the suite.',
    )
    parser.add_argument(
        '--model',
        dest='model',
        help="The model to run (one of 'mpas-ocean', 'omega', "
        "or 'mpas-seaice')",
    )
    args = parser.parse_args(sys.argv[2:])

    setup_suite(
        component=args.component,
        suite_name=args.task_suite,
        work_dir=args.work_dir,
        config_file=args.config_file,
        machine=args.machine,
        baseline_dir=args.baseline_dir,
        component_path=args.component_path,
        copy_executable=args.copy_executable,
        clean=args.clean,
        model=args.model,
    )


def _parse_suite(text):
    """Parse the text of a file defining a suite"""

    tasks: List[str] = list()
    cached: List[List[str]] = list()
    for task in text.split('\n'):
        task = task.strip()
        if len(task) == 0 or task.startswith('#'):
            # a blank line or comment
            continue

        if task == 'cached':
            cached[-1] = ['_all']
        elif task.startswith('cached:'):
            steps = task[len('cached:') :].strip().split(' ')
            cached[-1].extend(steps)
        else:
            tasks.append(task)
            cached.append(list())

    return tasks, cached
