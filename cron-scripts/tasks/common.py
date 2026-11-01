"""
What the nightly tasks share.  Tasks run inside a deployed Polaris
environment, launched by ``nightly.py`` once the load script for the
compiler has been sourced, so ``polaris`` and ``mache`` are importable and
``POLARIS_MACHINE``, ``POLARIS_COMPILER`` and ``POLARIS_BRANCH`` are set.
"""

import argparse
import glob
import importlib.util
import os
import shlex
import subprocess
import sys
import time

import yaml

from polaris.config import PolarisConfigParser
from polaris.job import write_job_script

# a job that builds Omega (and, for omega_cdash, runs its CTests) asks for the
# debug target, whose queue wait is minutes where the regular one's is hours,
# and so takes the debug wall-time limit of 30 minutes
BUILD_JOB_TARGET = 'debug'
BUILD_JOB_WALL_TIME = '0:30:00'


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
        With ``cron_root``, ``account``, ``model`` and ``site``, plus
        ``machine``, ``compiler`` and ``polaris_root`` from the environment
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--cron_root',
        required=True,
        help='The directory the nightly jobs work in',
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
    parser.add_argument(
        '--site',
        help='The site name shown on CDash (default: the machine); a test '
        'run of the nightly jobs should use its own',
    )
    parser.add_argument(
        '--build_jobs',
        type=int,
        help="Cap the Omega build at make -j BUILD_JOBS (default: Omega's "
        'own omega_build.sh)',
    )
    parser.add_argument(
        '--build_in_job',
        action='store_true',
        help='Build Omega in a job on a compute node rather than where the '
        'task runs',
    )
    args = parser.parse_args()
    args.cron_root = os.path.abspath(args.cron_root)
    args.machine = os.environ['POLARIS_MACHINE']
    if args.site is None:
        args.site = args.machine
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
        args.site,
        '--cdash_build_name',
        build_name,
        '--cdash_model',
        args.model,
    ]
    if args.account is not None:
        command.extend(['--account', args.account])
    if args.build_jobs is not None:
        command.extend(['--build_jobs', str(args.build_jobs)])
    command.extend(extra)
    return command


def run_omega_ctest(command, work_dir, args, job_name):
    """
    Run an ``omega_ctest.py`` command from ``work_dir``: here, or with
    ``--build_in_job`` in a one-node job, where ``omega_ctest.py`` sees that
    it is on a compute node and runs any CTests in the same job.

    Parameters
    ----------
    command : list of str
        From :py:func:`omega_ctest_command`

    work_dir : str
        Where to run it, and where the job script and its output go

    args : argparse.Namespace
        From :py:func:`parse_task_args`

    job_name : str
        The name of the job, and of its script and output
    """
    if not args.build_in_job:
        run(command, cwd=work_dir)
        return

    config = machine_config(args.machine)
    config.set('job', 'job_name', job_name)
    config.set('job', 'scheduler_target', BUILD_JOB_TARGET)
    config.set('job', 'wall_time', BUILD_JOB_WALL_TIME)
    if args.account is not None:
        config.set('parallel', 'account', args.account)

    job_script = os.path.join(work_dir, f'{job_name}.sh')
    write_job_script(
        config=config,
        machine=args.machine,
        work_dir=work_dir,
        nodes=1,
        script_filename=job_script,
        run_command=shlex.join(command),
    )

    output_pattern = os.path.join(work_dir, f'{job_name}.o*')
    for old_output in glob.glob(output_pattern):
        os.remove(old_output)
    try:
        submit_and_wait(job_script, config)
    finally:
        # the build and CTest output is in the job's output, not the task log
        for output in sorted(glob.glob(output_pattern)):
            print(f'\n===== {output} =====')
            with open(output, 'r', encoding='utf-8', errors='replace') as f:
                sys.stdout.write(f.read())
            sys.stdout.flush()


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
