import argparse
import importlib.resources as imp_res
import sys
from typing import List

from polaris.setup import setup_tasks


def setup_suite(
    component,
    suite_name,
    work_dir,
    **kwargs,
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

    work_dir : str
        A directory that will serve as the base for creating task
        directories

    kwargs : dict, optional
        Additional keyword arguments passed to ``setup_tasks``
    """

    text = (
        imp_res.files(f'polaris.suites.{component.replace("/", ".")}')
        .joinpath(f'{suite_name}.txt')
        .read_text()
    )

    tasks, cached = _parse_suite(text)

    setup_tasks(
        work_dir=work_dir,
        task_list=tasks,
        cached=cached,
        **kwargs,
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
        '--clean_work',
        dest='clean_work',
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
    parser.add_argument(
        '--build',
        dest='build',
        action='store_true',
        help='If the model should be built.',
    )
    parser.add_argument(
        '--branch',
        dest='branch',
        help='The branch of the model to build. The default is the submodule '
        'associated with the model',
    )
    parser.add_argument(
        '--clean_build',
        dest='clean_build',
        action='store_true',
        help='If the model should be cleaned before building. Implies '
        '--build.',
    )
    parser.add_argument(
        '--cmake_flags',
        dest='cmake_flags',
        help='Additional flags to pass to CMake when building the model.',
    )
    parser.add_argument(
        '--debug',
        dest='debug',
        action='store_true',
        help='If the model should be built in debug mode.',
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
        clean_work=args.clean_work,
        model=args.model,
        build=args.build,
        branch=args.branch,
        clean_build=args.clean_build,
        cmake_flags=args.cmake_flags,
        debug=args.debug,
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
