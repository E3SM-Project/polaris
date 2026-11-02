"""
The bug hunter's settings, from the ``[bug_hunt]`` section of the file the
PR testing utilities read
"""

import configparser
import os
from dataclasses import dataclass, field
from typing import List, Optional

#: where the settings are read from unless another file is given
DEFAULT_CONFIG = os.path.join('~', '.config', 'polaris_pr_test.cfg')

SECTION = 'bug_hunt'

#: the PR testing section, which the hunter reads ``omega_repo`` and
#: ``work_base`` from
PR_TEST_SECTION = 'polaris_pr_test'

#: the most decisions a digest asks for, besides P1 findings
DEFAULT_DECISIONS = 5

#: where responses from CDash are kept, since past nights do not change
DEFAULT_CACHE = os.path.join('~', '.cache', 'polaris_bug_hunt')


@dataclass
class HuntConfig:
    """
    The bug hunter's settings

    Attributes
    ----------
    ledger : str, optional
        A clone of the ledger repository, or ``None`` if none is set, in
        which case ``park`` prints a finding instead of recording it

    decisions : int
        The most decisions a digest asks for, besides P1 findings

    harvest_roots : list of str
        Polaris and CIME work directories to harvest

    cache : str
        Where responses from CDash are kept

    omega_repo : str, optional
        A clone of E3SM-Project/Omega, used to list the merges between two
        nights, from the PR testing settings

    work_base : str, optional
        Where campaigns set up builds and runs, from the PR testing
        settings
    """

    ledger: Optional[str] = None
    decisions: int = DEFAULT_DECISIONS
    harvest_roots: List[str] = field(default_factory=list)
    cache: str = field(default_factory=lambda: _expand(DEFAULT_CACHE))
    omega_repo: Optional[str] = None
    work_base: Optional[str] = None


def read_config(
    filename: Optional[str] = None, ledger: Optional[str] = None
) -> HuntConfig:
    """
    Read the settings, which may be missing

    Parameters
    ----------
    filename : str, optional
        The config file, :py:data:`DEFAULT_CONFIG` by default

    ledger : str, optional
        A ledger clone that overrides the one in the file

    Returns
    -------
    config : bug_hunt_config.HuntConfig
        The settings, with defaults for anything not set
    """
    config = HuntConfig()
    path = _expand(DEFAULT_CONFIG if filename is None else filename)
    if os.path.exists(path):
        parser = configparser.ConfigParser()
        parser.read(path)
        if parser.has_section(SECTION):
            config.ledger = _optional(parser, SECTION, 'ledger')
            config.decisions = parser.getint(
                SECTION, 'decisions', fallback=DEFAULT_DECISIONS
            )
            roots = parser.get(SECTION, 'harvest_roots', fallback='')
            config.harvest_roots = [
                _expand(root) for root in roots.replace(',', ' ').split()
            ]
            cache = _optional(parser, SECTION, 'cache')
            if cache is not None:
                config.cache = cache
        if parser.has_section(PR_TEST_SECTION):
            config.omega_repo = _optional(
                parser, PR_TEST_SECTION, 'omega_repo'
            )
            config.work_base = _optional(parser, PR_TEST_SECTION, 'work_base')
    if ledger is not None:
        config.ledger = _expand(ledger)
    return config


def _optional(parser, section, option):
    value = parser.get(section, option, fallback='').strip()
    return _expand(value) if value else None


def _expand(path):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
