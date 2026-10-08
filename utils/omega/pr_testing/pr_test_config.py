"""
The settings of the Omega PR testing utility, on the requester's computer
or on a machine
"""

import configparser
import os
import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Dict, List, Optional

from pr_test_manifest import SHARED_LOGIN_NODES

#: where the settings are read from unless another file is given
DEFAULT_CONFIG = os.path.join('~', '.config', 'omega_pr_test.cfg')

SECTION = 'omega_pr_test'

#: the section with the machines an agent on the requester's computer
#: tests over ssh
MACHINES_SECTION = 'machines'

_HOST = re.compile(r'^[\w.@-]+$')


class ConfigError(Exception):
    """The settings are missing, incomplete or invalid"""


@dataclass(frozen=True)
class RemoteMachine:
    """
    How an agent on the requester's computer reaches a machine over ssh

    Attributes
    ----------
    host : str
        The ssh host, usually an alias in the requester's ``~/.ssh/config``

    polaris_dir : str
        The Polaris checkout on the machine, as the machine's shell would
        expand it
    """

    host: str
    polaris_dir: str


@dataclass
class PrTestConfig:
    """
    The settings of the Omega PR testing utility

    Attributes
    ----------
    work_base : str
        The directory that Omega worktrees, baselines and test runs go in

    omega_repo : str
        A clone of E3SM-Project/Omega (or of a fork) that worktrees are made
        from

    fork : str, optional
        The requester's fork to push test branches to, needed only by the
        initiator

    polaris_fork : str, optional
        The requester's Polaris fork with any Polaris branches the testing
        needs, named in the testers' prompts; needed only by the initiator
        when testing with Polaris other than ``main``

    omega_dev_env : str, optional
        A conda environment made from Omega's ``dev-conda.txt``, needed only
        by the initiator when Omega's CI has not passed

    baseline_search_roots : list of str
        Other directories to look in for a baseline to reuse

    machines : dict of str to pr_test_config.RemoteMachine
        The machines an agent on the requester's computer tests over ssh,
        by Polaris machine; only on the requester's computer
    """

    work_base: str
    omega_repo: str
    fork: Optional[str] = None
    polaris_fork: Optional[str] = None
    omega_dev_env: Optional[str] = None
    baseline_search_roots: List[str] = field(default_factory=list)
    machines: Dict[str, RemoteMachine] = field(default_factory=dict)

    def find_machine(self, machine: str) -> Optional[RemoteMachine]:
        """
        How to reach a machine over ssh, or one that shares its login nodes

        Parameters
        ----------
        machine : str
            The Polaris machine

        Returns
        -------
        remote : pr_test_config.RemoteMachine, optional
            The machine's ``[machines]`` entry, or ``None`` if it has none
        """
        if machine in self.machines:
            return self.machines[machine]
        for group in SHARED_LOGIN_NODES:
            if machine in group:
                for other in sorted(group):
                    if other in self.machines:
                        return self.machines[other]
        return None


def read_config(filename: Optional[str] = None) -> PrTestConfig:
    """
    Read the settings

    Parameters
    ----------
    filename : str, optional
        The config file, :py:data:`DEFAULT_CONFIG` by default

    Returns
    -------
    config : pr_test_config.PrTestConfig
        The settings
    """
    if filename is None:
        filename = DEFAULT_CONFIG
    filename = _expand(filename)
    if not os.path.exists(filename):
        raise ConfigError(
            f'There is no config file at {filename}.  Copy '
            f'utils/omega/pr_testing/example.cfg there and fill it in.'
        )

    parser = configparser.ConfigParser()
    parser.read(filename)
    if not parser.has_section(SECTION):
        raise ConfigError(f'{filename} has no [{SECTION}] section.')

    missing = [
        option
        for option in ['work_base', 'omega_repo']
        if not parser.get(SECTION, option, fallback='').strip()
    ]
    if missing:
        raise ConfigError(
            f'{filename} does not set {" or ".join(missing)} in [{SECTION}].'
        )

    roots = parser.get(SECTION, 'baseline_search_roots', fallback='')
    return PrTestConfig(
        work_base=_expand(parser.get(SECTION, 'work_base')),
        omega_repo=_expand(parser.get(SECTION, 'omega_repo')),
        fork=_optional(parser, 'fork', expand=False),
        polaris_fork=_optional(parser, 'polaris_fork', expand=False),
        omega_dev_env=_optional(parser, 'omega_dev_env'),
        baseline_search_roots=[
            _expand(root) for root in roots.replace(',', ' ').split()
        ],
        machines=_read_machines(parser, filename),
    )


def _read_machines(parser, filename):
    """Read and check the ``[machines]`` section, if there is one"""
    if not parser.has_section(MACHINES_SECTION):
        return {}
    where = f'[{MACHINES_SECTION}] in {filename}'
    machines = {}
    for machine in parser.options(MACHINES_SECTION):
        if not _is_polaris_machine(machine):
            raise ConfigError(
                f'{where} names {machine}, which is not a Polaris machine.'
            )
        value = parser.get(MACHINES_SECTION, machine, raw=True).strip()
        host, _, polaris_dir = value.partition(':')
        host = host.strip()
        polaris_dir = polaris_dir.strip()
        if not _HOST.match(host) or not polaris_dir.startswith(('/', '~')):
            raise ConfigError(
                f'{where} gives {machine} as "{value}", not as '
                f'<ssh host>:<absolute path to Polaris on the machine>.'
            )
        machines[machine] = RemoteMachine(host, polaris_dir)

    for group in SHARED_LOGIN_NODES:
        given = sorted(group & set(machines))
        if len({machines[machine] for machine in given}) > 1:
            raise ConfigError(
                f'{where} gives {" and ".join(given)} differently, but '
                f'they are tested from the same login nodes.  Give one.'
            )
    return machines


def _is_polaris_machine(machine):
    """Whether Polaris has a config file for a machine"""
    if machine.startswith('default'):
        return False
    filename = f'{machine}.cfg'
    return resources.files('polaris.machines').joinpath(filename).is_file()


def _optional(parser, option, expand=True):
    value = parser.get(SECTION, option, fallback='').strip()
    if not value:
        return None
    return _expand(value) if expand else value


def _expand(path):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
