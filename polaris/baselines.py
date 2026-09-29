"""
Find existing suite runs and builds that can serve as a baseline

A run can be reused as a baseline only if its provenance shows that it ran
the same suite, with the same Polaris, on the same machine and compiler,
from a build of the same component commit, and that every task passed.
The component commit has to come from the record Polaris's build scripts
write, since a commit read from the source tree at setup may not be the one
that was built.
"""

import json
import os
import shlex
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Tuple

from polaris.build.omega import detect_omega_build_type, get_omega_cime_target
from polaris.build.source_record import read_source_record
from polaris.provenance import read as read_provenance

# how far below each search root to look for runs and builds
MAX_SEARCH_DEPTH = 3


@dataclass(frozen=True)
class BaselineCriteria:
    """
    What a run or build must have been made with to serve as a baseline

    Attributes
    ----------
    machine : str
        The machine the run or build was made on

    compiler : str
        The compiler the component was built with

    build_type : str
        The build type of the component, ``Release`` or ``Debug``

    component_hash : str
        The full hash of the component commit that was built

    polaris_hash : str
        The full hash of the Polaris commit that set up the run

    suite : str
        The name of the suite
    """

    machine: str
    compiler: str
    build_type: str
    component_hash: str
    polaris_hash: str
    suite: str = 'omega_pr'


@dataclass
class NearMiss:
    """
    A run or build that was considered but does not match

    Attributes
    ----------
    path : str
        The work directory of the run, or the build directory

    reasons : list of str
        Why it does not match
    """

    path: str
    reasons: List[str] = field(default_factory=list)


def find_baseline(
    roots: Iterable[str], criteria: BaselineCriteria
) -> Tuple[List[str], List[NearMiss]]:
    """
    Find suite runs that match the criteria for a baseline

    A candidate is a directory at most :py:data:`MAX_SEARCH_DEPTH` levels
    below a search root with the suite's pickle file, which ``polaris
    suite`` writes to the base work directory.

    Parameters
    ----------
    roots : iterable of str
        The directories to search

    criteria : polaris.baselines.BaselineCriteria
        What a baseline must have been made with

    Returns
    -------
    matches : list of str
        The work directories of the runs that match

    near_misses : list of polaris.baselines.NearMiss
        The other candidates and why each does not match, fewest reasons
        first
    """
    matches = []
    near_misses = []
    marker = f'{criteria.suite}.pickle'
    for work_dir in _find_dirs_with(roots, marker):
        reasons = check_baseline(work_dir, criteria)
        if reasons:
            near_misses.append(NearMiss(work_dir, reasons))
        else:
            matches.append(work_dir)
    near_misses.sort(key=lambda near_miss: len(near_miss.reasons))
    return matches, near_misses


def check_baseline(work_dir: str, criteria: BaselineCriteria) -> List[str]:
    """
    Check whether a suite run matches the criteria for a baseline

    Parameters
    ----------
    work_dir : str
        The base work directory of the suite run

    criteria : polaris.baselines.BaselineCriteria
        What a baseline must have been made with

    Returns
    -------
    reasons : list of str
        Why the run does not match, empty if it does
    """
    provenance = read_provenance(work_dir)
    if provenance is None:
        return ['it has no provenance file']

    reasons = []
    for label in ['machine', 'compiler', 'build type']:
        value = provenance.get(label)
        expected = getattr(criteria, label.replace(' ', '_'))
        if value != expected:
            reasons.append(f'its {label} is {value}, not {expected}')

    reasons.extend(
        _commit_problems(
            'component', provenance['component'], criteria.component_hash
        )
    )
    reasons.extend(
        _commit_problems(
            'Polaris', provenance['polaris'], criteria.polaris_hash
        )
    )
    reasons.extend(
        _command_problems(provenance.get('command'), criteria.suite)
    )
    reasons.extend(_results_problems(work_dir, criteria.suite))
    return reasons


def find_build_log(
    roots: Iterable[str], criteria: BaselineCriteria
) -> Tuple[List[str], List[NearMiss]]:
    """
    Find complete build logs of the baseline's component commit

    Only the machine, compiler, build type and component commit of the
    criteria apply to a build.  A candidate is a directory at most
    :py:data:`MAX_SEARCH_DEPTH` levels below a search root with a source
    record, or the build directory of a suite run found there.

    Parameters
    ----------
    roots : iterable of str
        The directories to search

    criteria : polaris.baselines.BaselineCriteria
        What the build must have been made with

    Returns
    -------
    logs : list of str
        The build logs of the builds that match

    near_misses : list of polaris.baselines.NearMiss
        The other builds and why each does not match, fewest reasons first
    """
    roots = list(roots)
    build_dirs = list(_find_dirs_with(roots, 'omega_source.txt'))
    for work_dir in _find_dirs_with(roots, f'{criteria.suite}.pickle'):
        provenance = read_provenance(work_dir)
        if provenance is not None and provenance.get('build directory'):
            build_dirs.append(provenance['build directory'])

    logs = []
    near_misses = []
    seen = set()
    for build_dir in build_dirs:
        real_path = os.path.realpath(build_dir)
        if real_path in seen:
            continue
        seen.add(real_path)
        reasons = check_build(build_dir, criteria)
        if reasons:
            near_misses.append(NearMiss(build_dir, reasons))
        else:
            logs.append(os.path.join(build_dir, 'build_omega.log'))
    near_misses.sort(key=lambda near_miss: len(near_miss.reasons))
    return logs, near_misses


def check_build(build_dir: str, criteria: BaselineCriteria) -> List[str]:
    """
    Check whether an Omega build has a complete log of a build that matches
    the criteria

    Parameters
    ----------
    build_dir : str
        The build directory

    criteria : polaris.baselines.BaselineCriteria
        What the build must have been made with

    Returns
    -------
    reasons : list of str
        Why the build does not match, empty if it does
    """
    record = read_source_record(build_dir)
    if record is None:
        return ['it has no source record']

    reasons = []
    machine, compiler = get_omega_cime_target(build_dir)
    build_type = detect_omega_build_type(build_dir)
    for label, value, expected in [
        ('machine', machine, criteria.machine),
        ('compiler', compiler, criteria.compiler),
        ('build type', build_type, criteria.build_type),
    ]:
        if value != expected:
            reasons.append(f'its {label} is {value}, not {expected}')

    info = {
        'describe': record['describe'],
        'hash': record['hash'],
        'at_setup': False,
    }
    reasons.extend(
        _commit_problems('component', info, criteria.component_hash)
    )
    if not record['clean_build']:
        reasons.append('it was not built from an empty build directory')
    if not os.path.exists(os.path.join(build_dir, 'src', 'omega.exe')):
        reasons.append('it has no omega.exe, so the build did not finish')
    if not os.path.exists(os.path.join(build_dir, 'build_omega.log')):
        reasons.append('it has no build_omega.log')
    return reasons


def _find_dirs_with(roots: Iterable[str], filename: str) -> Iterator[str]:
    """
    Directories at most MAX_SEARCH_DEPTH levels below each root that
    contain the file, without looking inside the ones that do
    """
    seen = set()
    for root in roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        root_depth = root.rstrip(os.sep).count(os.sep)
        for dir_path, dir_names, file_names in os.walk(root):
            if filename in file_names:
                dir_names[:] = []
                real_path = os.path.realpath(dir_path)
                if real_path not in seen:
                    seen.add(real_path)
                    yield dir_path
                continue
            if dir_path.count(os.sep) - root_depth >= MAX_SEARCH_DEPTH:
                dir_names[:] = []
            else:
                dir_names[:] = [
                    name for name in dir_names if not name.startswith('.')
                ]


def _commit_problems(
    name: str, info: Optional[dict], expected_hash: str
) -> List[str]:
    if info is None or info['hash'] is None:
        return [f'it does not record its {name} commit']
    reasons = []
    if info['hash'] != expected_hash:
        reasons.append(
            f'its {name} commit is {info["hash"][:12]}, '
            f'not {expected_hash[:12]}'
        )
    if info['at_setup']:
        reasons.append(
            f'its {name} commit was recorded at setup, not when it was built'
        )
    if (info['describe'] or '').endswith('-dirty'):
        reasons.append(f'its {name} tree had uncommitted changes')
    return reasons


def _command_problems(command: Optional[str], suite: str) -> List[str]:
    if command is None:
        return ['it does not record the command that set it up']
    try:
        args = shlex.split(command)
    except ValueError:
        return ['the command that set it up could not be parsed']

    if len(args) < 2 or args[1] != 'suite':
        return ['it was not set up with "polaris suite"']

    reasons = []
    set_up_suite = _option_value(args, ['-t', '--task_suite'])
    if set_up_suite != suite:
        reasons.append(f'it was set up as suite {set_up_suite}, not {suite}')
    config_file = _option_value(args, ['-f', '--config_file'])
    if config_file is not None:
        reasons.append(f'it was set up with config file {config_file}')
    if _option_value(args, ['--cmake_flags']) is not None:
        reasons.append('it was set up with --cmake_flags')
    return reasons


def _option_value(args: List[str], names: List[str]) -> Optional[str]:
    """The value of the last of the named options in args, if any"""
    value = None
    for index, arg in enumerate(args):
        name, separator, inline_value = arg.partition('=')
        if name not in names:
            continue
        if separator:
            value = inline_value
        elif index + 1 < len(args):
            value = args[index + 1]
    return value


def _results_problems(work_dir: str, suite: str) -> List[str]:
    path = os.path.join(work_dir, f'{suite}_results.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except (OSError, ValueError):
        return [f'it has no readable {suite}_results.json']

    summary = results.get('summary', {})
    reasons = []
    if not results.get('complete', False):
        reasons.append('its run is not complete')
    for status, verb in [('failed', 'failed'), ('pending', 'did not run')]:
        count = summary.get(status, 0)
        if count:
            reasons.append(f'{count} of its tasks {verb}')
    return reasons
