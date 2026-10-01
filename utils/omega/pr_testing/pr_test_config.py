"""
The per-machine settings of the Omega PR testing utility
"""

import configparser
import os
from dataclasses import dataclass, field
from typing import List, Optional

#: where the settings are read from unless another file is given
DEFAULT_CONFIG = os.path.join('~', '.config', 'omega_pr_test.cfg')

SECTION = 'omega_pr_test'


class ConfigError(Exception):
    """The settings are missing or incomplete"""


@dataclass
class PrTestConfig:
    """
    The per-machine settings of the Omega PR testing utility

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
    """

    work_base: str
    omega_repo: str
    fork: Optional[str] = None
    polaris_fork: Optional[str] = None
    omega_dev_env: Optional[str] = None
    baseline_search_roots: List[str] = field(default_factory=list)


def read_config(filename: Optional[str] = None) -> PrTestConfig:
    """
    Read the per-machine settings

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
    )


def _optional(parser, option, expand=True):
    value = parser.get(SECTION, option, fallback='').strip()
    if not value:
        return None
    return _expand(value) if expand else value


def _expand(path):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
