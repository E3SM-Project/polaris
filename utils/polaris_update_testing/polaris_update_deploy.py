"""
Deploying the Spack environments of a Polaris version update, and telling
which environments a load script uses
"""

import configparser
import glob
import importlib.metadata
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import mache
import pr_test_setup as setup_tools
from packaging.version import Version
from polaris_update_manifest import fetch_manifest, read_rows
from pr_test_config import PrTestConfig
from pr_test_git import POLARIS_DIR
from pr_test_rows import Row, get_machine_rows

from polaris.machines import discover_machine

#: the variable a load script sets to the Spack environment it uses
SPACK_VIEW_VARIABLE = 'MACHE_DEPLOY_SPACK_LIBRARY_VIEW'


class DeployError(Exception):
    """The environments could not be deployed, or are not as expected"""


@dataclass
class Deployment:
    """
    What deploying a machine's environments takes, and what came of it

    Attributes
    ----------
    machine : str
        The Polaris machine

    command : list of str
        The ``./deploy.py`` command, run in the Polaris checkout

    spack_path : str
        Where the Spack environments go

    log : str
        Where the command's output goes

    ran : bool
        Whether the command was run

    missing : list of str
        The rows with no load script that uses the environments
    """

    machine: str
    command: List[str]
    spack_path: str
    log: str
    ran: bool = False
    missing: List[str] = field(default_factory=list)


def run_deploy(
    config: PrTestConfig,
    fork: str,
    branch: str,
    machine: Optional[str] = None,
    spack_path: Optional[str] = None,
    recreate: bool = False,
    run: bool = False,
    polaris_dir: str = POLARIS_DIR,
    mache_fork: Optional[str] = None,
    mache_branch: Optional[str] = None,
) -> List[Deployment]:
    """
    Deploy, or show how to deploy, the Spack environments for a machine's
    rows, and check the load scripts

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's Polaris fork

    branch : str
        The test branch

    machine : str, optional
        The machine, the one this runs on by default.  Pm-cpu and pm-gpu
        are deployed one after the other.

    spack_path : str, optional
        Where to deploy test environments; the shared environments by
        default

    recreate : bool, optional
        Whether to recreate environments that exist

    run : bool, optional
        Whether to run the deployment

    polaris_dir : str, optional
        The Polaris checkout to deploy from

    mache_fork : str, optional
        The mache fork, such as ``E3SM-Project/mache``, to deploy with a
        mache branch that is not released yet

    mache_branch : str, optional
        The mache branch on ``mache_fork``

    Returns
    -------
    deployments : list of polaris_update_deploy.Deployment
        A deployment for each machine
    """
    if (mache_fork is None) != (mache_branch is None):
        raise DeployError(
            'Pass both --mache-fork and --mache-branch, or neither.'
        )
    manifest = fetch_manifest(polaris_dir, fork, branch)
    setup_tools.check_checkout(polaris_dir, manifest.pr_head, 'PR head')
    if machine is None:
        machine = discover_machine(quiet=True)
    if machine is None:
        raise DeployError('This is not a Polaris machine.  Pass --machine.')
    rows = get_machine_rows(manifest.rows, machine)
    if not rows:
        raise DeployError(f'The manifest has no rows for {machine}.')
    if spack_path is not None:
        spack_path = os.path.abspath(os.path.expanduser(spack_path))

    # every row the PR supports, even if the manifest tests only some
    supported = read_rows(polaris_dir, manifest.pr_head)
    deployments = []
    for row_machine in dict.fromkeys(row.machine for row in rows):
        path = spack_path or get_shared_spack_path(
            polaris_dir, row_machine, manifest.test.polaris_version
        )
        command = get_deploy_command(
            row_machine,
            [row for row in supported if row.machine == row_machine],
            spack_path,
            recreate,
            mache_fork,
            mache_branch,
        )
        log = os.path.join(
            config.work_base, manifest.run_name, f'deploy_{row_machine}.log'
        )
        deployments.append(Deployment(row_machine, command, path, log))

    for deployment in deployments:
        if run:
            _deploy(deployment, polaris_dir)
        machine_rows = [
            row for row in rows if row.machine == deployment.machine
        ]
        deployment.missing = check_load_scripts(
            polaris_dir, machine_rows, deployment.spack_path
        )
    return deployments


def get_deploy_command(
    machine: str,
    rows: List[Row],
    spack_path: Optional[str] = None,
    recreate: bool = False,
    mache_fork: Optional[str] = None,
    mache_branch: Optional[str] = None,
) -> List[str]:
    """
    The command that deploys the Spack environments for the compilers and
    MPI libraries of a machine's supported rows

    Parameters
    ----------
    machine : str
        The Polaris machine

    rows : list of pr_test_rows.Row
        The rows the PR supports on the machine

    spack_path : str, optional
        Where to deploy test environments; the shared environments by
        default

    recreate : bool, optional
        Whether to recreate environments that exist

    mache_fork : str, optional
        The mache fork to deploy a mache branch from

    mache_branch : str, optional
        The mache branch on ``mache_fork``

    Returns
    -------
    command : list of str
        The command, run in the checkout
    """
    pairs = list(dict.fromkeys((row.compiler, row.mpi) for row in rows))
    if not pairs:
        raise DeployError(f'The PR supports no rows on {machine}.')
    command = ['./deploy.py', '--deploy-spack', '--machine', machine]
    command += ['--compiler'] + [compiler for compiler, _ in pairs]
    command += ['--mpi'] + [mpi for _, mpi in pairs]
    if spack_path is not None:
        command += ['--spack-path', spack_path]
    if recreate:
        command.append('--recreate')
    if mache_fork is not None and mache_branch is not None:
        command += ['--mache-fork', mache_fork, '--mache-branch', mache_branch]
    return command


def get_shared_spack_path(polaris_dir: str, machine: str, version: str) -> str:
    """
    Where a Polaris version's shared Spack environments go on a machine

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout, whose machine config is read

    machine : str
        The Polaris machine

    version : str
        The Polaris version

    Returns
    -------
    spack_path : str
        The shared Spack path, as ``deploy/hooks.py`` makes it
    """
    base = _read_machine_config(polaris_dir, machine).get(
        'deploy', 'spack', fallback=''
    )
    if not base.strip():
        raise DeployError(f'Polaris has no shared Spack path for {machine}.')
    release = Version(version).base_version
    return os.path.join(base.strip(), f'dev_polaris_{release}')


def read_environment(polaris_dir: str, machine: str) -> Dict[str, str]:
    """
    The Spack environment the loaded load script uses, and whether it is
    the shared one

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout, whose machine config is read

    machine : str
        The Polaris machine

    Returns
    -------
    environment : dict
        ``spack``, ``shared`` or ``test``; ``spack_path``; the
        ``polaris_version`` and ``mache_version`` loaded; and
        ``mache_source``, ``branch`` if mache was installed from a branch
        and ``release`` otherwise
    """
    view = os.environ.get(SPACK_VIEW_VARIABLE, '').strip()
    if not view:
        raise DeployError(
            f'The loaded load script sets no {SPACK_VIEW_VARIABLE}, so it '
            f'uses no Spack environment.  Source a load script from a '
            f'deployment with Spack.'
        )
    return {
        'spack': get_spack_kind(polaris_dir, machine, view),
        'spack_path': get_spack_path(view),
        'polaris_version': os.environ.get('POLARIS_VERSION', ''),
        'mache_version': mache.__version__,
        'mache_source': get_mache_source(),
    }


def get_mache_source() -> str:
    """
    ``branch`` if the loaded mache was installed by pip from a directory,
    as ``./deploy.py --mache-fork --mache-branch`` installs it from its
    clone of the branch, and ``release`` otherwise
    """
    # an environment can also hold the metadata of an older mache, under
    # the old name ``mache``, so use the one with the loaded version
    for name in importlib.metadata.packages_distributions().get('mache', []):
        distribution = importlib.metadata.distribution(name)
        if distribution.version == mache.__version__:
            return _get_install_source(distribution)
    return 'release'


def _get_install_source(distribution) -> str:
    """``branch`` if a distribution was installed by pip from a directory"""
    # a conda package's metadata also has a direct_url.json with dir_info,
    # pointing to where it was built, but its installer is conda
    installer = (distribution.read_text('INSTALLER') or '').strip()
    direct_url = distribution.read_text('direct_url.json')
    if installer == 'conda' or not direct_url:
        return 'release'
    try:
        from_directory = 'dir_info' in json.loads(direct_url)
    except json.JSONDecodeError:
        from_directory = False
    return 'branch' if from_directory else 'release'


def get_spack_kind(polaris_dir: str, machine: str, view: str) -> str:
    """
    ``shared`` if a Spack view is under the machine's shared Spack path,
    and ``test`` otherwise
    """
    base = _read_machine_config(polaris_dir, machine).get(
        'deploy', 'spack', fallback=''
    )
    if base.strip() and _is_under(view, base.strip()):
        return 'shared'
    return 'test'


def get_spack_path(view: str) -> str:
    """The Spack checkout a Spack environment's view is in"""
    marker = f'{os.sep}var{os.sep}spack{os.sep}'
    if marker in view:
        return view.split(marker)[0]
    return view


def check_load_scripts(
    polaris_dir: str, rows: List[Row], spack_path: str
) -> List[str]:
    """
    The rows with no load script in the checkout that uses a Spack path

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout

    rows : list of pr_test_rows.Row
        The rows

    spack_path : str
        Where the environments were deployed

    Returns
    -------
    missing : list of str
        The rows, as ``<machine>/<compiler>``, with no such load script
    """
    missing = []
    for machine, compiler, mpi in dict.fromkeys(
        (row.machine, row.compiler, row.mpi) for row in rows
    ):
        pattern = os.path.join(
            polaris_dir, f'load_polaris*_{machine}_{compiler}_{mpi}.sh'
        )
        found = False
        for load_script in glob.glob(pattern):
            with open(load_script, 'r', encoding='utf-8') as f:
                exports = setup_tools.read_exports(f.read())
            view = exports.get(SPACK_VIEW_VARIABLE, '')
            if view and _is_under(view, spack_path):
                found = True
        if not found:
            missing.append(f'{machine}/{compiler}')
    return missing


def format_deployments(deployments: List[Deployment], polaris_dir: str) -> str:
    """The summary deploy prints"""
    lines = []
    for deployment in deployments:
        command = shlex.join(deployment.command)
        lines.append(f'{deployment.machine}: {deployment.spack_path}')
        if deployment.ran:
            lines.append(f'  Deployed.  Log: {deployment.log}')
        else:
            lines.append(
                f"  Not deployed.  With the requester's permission, run "
                f'deploy again with --run, which runs:\n'
                f'    cd {polaris_dir} && {command}'
            )
        if deployment.missing:
            lines.append(
                f'  No load script uses these environments yet for: '
                f'{", ".join(deployment.missing)}'
            )
        else:
            lines.append('  Every row has a load script that uses them.')
    return '\n'.join(lines)


def _deploy(deployment: Deployment, polaris_dir: str) -> None:
    """
    Run a deployment in a clean login shell, so that the environment loaded
    to run this utility does not reach it, with its output in its log
    """
    os.makedirs(os.path.dirname(deployment.log), exist_ok=True)
    print(
        f'\nRunning in {polaris_dir}, in a clean login shell:\n'
        f'  {shlex.join(deployment.command)}\n'
        f'with its output in {deployment.log}\n',
        flush=True,
    )
    env = {
        name: os.environ[name]
        for name in setup_tools.LOGIN_ENV_VARS
        if name in os.environ
    }
    command = (
        f'cd {shlex.quote(polaris_dir)} && {shlex.join(deployment.command)}'
    )
    with open(deployment.log, 'w', encoding='utf-8') as log:
        completed = subprocess.run(
            ['/bin/bash', '-l', '-c', command],
            cwd=polaris_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if completed.returncode != 0:
        raise DeployError(
            f'Deploying on {deployment.machine} failed; see {deployment.log}.'
        )
    deployment.ran = True


def _read_machine_config(polaris_dir, machine):
    """A machine's config as the checkout has it"""
    path = os.path.join(polaris_dir, 'polaris', 'machines', f'{machine}.cfg')
    if not os.path.exists(path):
        raise DeployError(f'Polaris has no config for {machine}.')
    config = configparser.ConfigParser(default_section='__no_defaults__')
    config.read(path)
    if not config.has_section('deploy'):
        raise DeployError(f'{path} has no [deploy] section.')
    return config


def _is_under(path, base):
    """Whether a path is a base directory or inside it"""
    path = os.path.normpath(path)
    base = os.path.normpath(base)
    return path == base or path.startswith(f'{base}{os.sep}')
