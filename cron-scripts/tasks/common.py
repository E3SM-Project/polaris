"""
What the nightly tasks share.  Tasks run inside a deployed Polaris
environment, launched by ``nightly.py`` once the load script for the
compiler has been sourced, so ``polaris`` and ``mache`` are importable and
``POLARIS_MACHINE``, ``POLARIS_COMPILER`` and ``POLARIS_BRANCH`` are set.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import time

import yaml

from polaris.config import PolarisConfigParser


def parse_task_args(description):
    """
    Parse the command line every nightly task accepts.

    Parameters
    ----------
    description : str
        For ``--help``

    Returns
    -------
    args : argparse.Namespace
        With ``cron_root``, ``arch``, ``account`` and ``model``, plus
        ``machine``, ``compiler`` and ``polaris_root`` from the environment
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--cron_root',
        required=True,
        help='The directory the nightly jobs work in',
    )
    parser.add_argument(
        '--arch',
        required=True,
        help='The Omega architecture to build (OMEGA_ARCH)',
    )
    parser.add_argument(
        '--account',
        help='The account to charge jobs to, if the machine default is not '
        'the right one',
    )
    parser.add_argument(
        '--model',
        default='Nightly',
        choices=['Nightly', 'Experimental', 'Continuous'],
        help='The CTest model (default: Nightly)',
    )
    args = parser.parse_args()
    args.cron_root = os.path.abspath(args.cron_root)
    args.machine = os.environ['POLARIS_MACHINE']
    args.compiler = os.environ['POLARIS_COMPILER']
    args.polaris_root = os.environ['POLARIS_BRANCH']

    check_supported_compiler(args.polaris_root, args.machine, args.compiler)
    return args


def check_supported_compiler(polaris_root, machine, compiler):
    """
    Raise if the compiler is not one the Developer's Guide lists for Omega on
    this machine, so the cron config cannot drift from the documentation.
    """
    filename = os.path.join(
        polaris_root, 'docs', 'developers_guide', 'supported_machines.yaml'
    )
    with open(filename, 'r', encoding='utf-8') as f:
        supported = yaml.safe_load(f)

    for entry in supported['machines']:
        if entry['name'] != machine:
            continue
        compilers = [
            model['compiler']
            for model in entry['models']
            if model['model'] == 'Omega' and model['compiler'] is not None
        ]
        if compiler in compilers:
            return
        raise ValueError(
            f'{compiler} is not a supported Omega compiler on {machine} '
            f'according to {filename}; it has: {", ".join(compilers)}'
        )
    raise ValueError(f'{machine} is not listed in {filename}')


def load_omega_ctest(polaris_root):
    """
    Import ``utils/omega/ctest/omega_ctest.py`` as a module, so tasks can
    build its ``ctest -S`` commands rather than repeating them.
    """
    filename = os.path.join(
        polaris_root, 'utils', 'omega', 'ctest', 'omega_ctest.py'
    )
    spec = importlib.util.spec_from_file_location('omega_ctest', filename)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot import {filename}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def omega_ctest_command(polaris_root, args, branch, build_name, extra):
    """
    The ``omega_ctest.py`` command line a task runs to build Omega for CDash.

    Parameters
    ----------
    polaris_root : str
        The Polaris clone

    args : argparse.Namespace
        From :py:func:`parse_task_args`

    branch : str
        The Omega branch to build

    build_name : str
        The build name shown on CDash

    extra : list of str
        Further options for the utility

    Returns
    -------
    command : list of str
    """
    utility = os.path.join(
        polaris_root, 'utils', 'omega', 'ctest', 'omega_ctest.py'
    )
    command = [
        utility,
        '--omega_branch',
        branch,
        '--clean',
        '--dashboard',
        '--cdash_site',
        args.machine,
        '--cdash_build_name',
        build_name,
        '--cdash_model',
        args.model,
        '--cmake_flags',
        f'-DOMEGA_ARCH={args.arch}',
    ]
    if args.account is not None:
        command.extend(['--account', args.account])
    command.extend(extra)
    return command


def machine_config(machine):
    """
    The Polaris config for a machine, without any task or component config.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    config.add_from_package('polaris.machines', f'{machine}.cfg')
    return config


def run(command, cwd=None):
    """
    Run a command, echoing it first, and raise if it fails.
    """
    print(f'\n[{_now()}] in {cwd or os.getcwd()}:\n   {" ".join(command)}\n')
    sys.stdout.flush()
    subprocess.run(command, cwd=cwd, check=True)


def submit_and_wait(job_script, config):
    """
    Submit a job script and block until the job finishes.

    Parameters
    ----------
    job_script : str
        The job script, run from its own directory

    config : polaris.config.PolarisConfigParser
        Machine config, for the scheduler
    """
    system = config.get('parallel', 'system')
    if system == 'slurm':
        command = ['sbatch', '--wait', os.path.basename(job_script)]
    elif system == 'pbs':
        command = ['qsub', '-W', 'block=true', os.path.basename(job_script)]
    else:
        raise ValueError(f'Unsupported parallel system: {system}')
    run(command, cwd=os.path.dirname(os.path.abspath(job_script)))


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')
