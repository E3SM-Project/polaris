"""
Find the compiler warnings a PR build has that its baseline build does not

A warning is identified by its source path relative to the Omega tree (or
the build directory), its message and its flag, but not its line number, so
that a PR that adds lines above an existing warning does not make it look
new.  A warning that the baseline build does not have is new.  So is one
that appears more often in the PR build, but only in a file the PR changes:
elsewhere, a header's warning appears once for each file that includes it,
and a parallel build can garble a line of the log beyond recognition, so a
higher count says nothing about the PR's code.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

from polaris.build.source_record import read_source_record

_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# GCC, Clang and the oneAPI C and C++ compilers
_GCC = re.compile(
    r'^(?P<path>[^\s:][^:]*):(?P<line>\d+):(?:\d+:)?\s+warning:\s+'
    r'(?P<message>.*?)(?:\s+\[(?P<flag>-W[^\]]+)\])?\s*$'
)

# NVCC (EDG) and ifx
_EDG = re.compile(
    r'^(?P<path>[^\s(][^(]*)\((?P<line>\d+)\):\s+warning\s+'
    r'#(?P<code>[\w-]+):\s+(?P<message>.*?)\s*$'
)

# gfortran gives the location on a line of its own, then the warning
_GFORTRAN_LOCATION = re.compile(r'^(?P<path>[^\s:][^:]*):(?P<line>\d+):\d+:$')
_GFORTRAN_WARNING = re.compile(
    r'^Warning:\s+(?P<message>.*?)(?:\s+\[(?P<flag>-W[^\]]+)\])?\s*$'
)

_CMAKE = re.compile(
    r'^CMake Warning(?: \(dev\))? at (?P<path>[^:]+):(?P<line>\d+)'
)


@dataclass(frozen=True)
class BuildWarning:
    """
    A compiler or CMake warning, without its line number

    Attributes
    ----------
    path : str
        The file, relative to the Omega tree (or prefixed ``<build>/`` if it
        is in the build directory)

    flag : str
        The warning flag, such as ``-Wreturn-type``, the warning number, such
        as ``#5472``, ``CMake`` for a CMake warning, or empty

    message : str
        The warning's message, with the Omega tree and build directory
        replaced by ``<omega>`` and ``<build>``
    """

    path: str
    flag: str
    message: str

    def format(self) -> str:
        """The warning on one line"""
        flag = f' [{self.flag}]' if self.flag else ''
        return f'{self.path}:{flag} {self.message}'


def parse_build_log(
    log_path: str, source_root: Optional[str], build_dir: Optional[str]
) -> 'Counter[BuildWarning]':
    """
    Count the warnings in a build log

    Parameters
    ----------
    log_path : str
        The build log

    source_root : str, optional
        The Omega tree the build was made from

    build_dir : str, optional
        The build directory

    Returns
    -------
    warnings : collections.Counter
        How often each warning appears
    """
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    return Counter(_parse_lines(lines, source_root, build_dir))


def read_build_warnings(build_dir: str) -> Optional['Counter[BuildWarning]']:
    """
    Count the warnings in a build's log, using the build's source record to
    find the Omega tree

    Parameters
    ----------
    build_dir : str
        The build directory

    Returns
    -------
    warnings : collections.Counter or None
        How often each warning appears, or ``None`` if the build has no
        complete log from an empty build directory
    """
    record = read_source_record(build_dir)
    log_path = os.path.join(build_dir, 'build_omega.log')
    if record is None or not record['clean_build']:
        return None
    if not os.path.exists(log_path):
        return None
    return parse_build_log(log_path, record['source'], build_dir)


def find_new_warnings(
    baseline: 'Counter[BuildWarning]',
    pr: 'Counter[BuildWarning]',
    changed_files: Iterable[str] = (),
) -> List[Tuple[BuildWarning, int, int]]:
    """
    The warnings the baseline build does not have, and those in files the
    PR changes that appear more often in the PR build

    Parameters
    ----------
    baseline : collections.Counter
        The warnings in the baseline build

    pr : collections.Counter
        The warnings in the PR build

    changed_files : iterable of str, optional
        The files the PR changes, relative to the Omega tree

    Returns
    -------
    new : list of tuple
        Each new warning with its baseline and PR counts, sorted by path
    """
    changed = set(changed_files)
    new = [
        (warning, baseline[warning], count)
        for warning, count in pr.items()
        if baseline[warning] == 0
        or (warning.path in changed and count > baseline[warning])
    ]
    return sorted(new, key=lambda item: (item[0].path, item[0].message))


def format_warnings_section(
    baseline_build_dir: Optional[str],
    pr_build_dir: str,
    changed_files: Iterable[str],
) -> Tuple[str, Optional[int]]:
    """
    The Build warnings section of a report

    Parameters
    ----------
    baseline_build_dir : str, optional
        A build of the baseline commit, if one with a complete log was found

    pr_build_dir : str
        The PR build

    changed_files : iterable of str
        The files the PR changes, relative to the Omega tree

    Returns
    -------
    text : str
        The section

    new_count : int or None
        The number of new warnings, or ``None`` if they could not be
        compared
    """
    heading = '### Build warnings'
    pr = read_build_warnings(pr_build_dir)
    if pr is None:
        return (
            f'{heading}\n\nNot compared: the PR build in `{pr_build_dir}` has '
            f'no complete log from an empty build directory.',
            None,
        )
    if baseline_build_dir is None:
        return (
            f'{heading}\n\nNot compared: no complete build log of the '
            f'baseline commit was found.',
            None,
        )
    baseline = read_build_warnings(baseline_build_dir)
    if baseline is None:
        return (
            f'{heading}\n\nNot compared: the baseline build in '
            f'`{baseline_build_dir}` has no complete log from an empty build '
            f'directory.',
            None,
        )

    changed: Set[str] = set(changed_files)
    new = find_new_warnings(baseline, pr, changed)
    logs = (
        f'- Baseline build log: '
        f'`{os.path.join(baseline_build_dir, "build_omega.log")}`\n'
        f'- PR build log: `{os.path.join(pr_build_dir, "build_omega.log")}`'
    )
    totals = (
        f'{sum(pr.values())} in the PR build, {sum(baseline.values())} in '
        f'the baseline build'
    )
    if not new:
        return f'{heading}\n\nNo new warnings ({totals}).\n\n{logs}', 0

    in_changed = sum(1 for warning, _, _ in new if warning.path in changed)
    lines = [
        heading,
        '',
        f'{len(new)} new warnings, {in_changed} in files this PR changes '
        f'({totals}).  Those in files the PR changes are marked `*`.',
        '',
        '<details>',
        '<summary>New warnings</summary>',
        '',
        '```',
    ]
    for warning, baseline_count, pr_count in new:
        mark = '* ' if warning.path in changed else '  '
        counts = ''
        if baseline_count or pr_count > 1:
            counts = f' ({baseline_count} -> {pr_count})'
        lines.append(f'{mark}{warning.format()}{counts}')
    lines.extend(['```', '</details>', '', logs])
    return '\n'.join(lines), len(new)


def _parse_lines(lines, source_root, build_dir):
    location = None
    cmake_path = None
    for raw in lines:
        line = _ANSI.sub('', raw).rstrip()

        if cmake_path is not None:
            if line.strip():
                yield _make(
                    cmake_path, 'CMake', line.strip(), source_root, build_dir
                )
                cmake_path = None
            continue

        match = _GCC.match(line)
        if match is not None:
            yield _make(
                match['path'],
                match['flag'] or '',
                match['message'],
                source_root,
                build_dir,
            )
            location = None
            continue

        match = _EDG.match(line)
        if match is not None:
            yield _make(
                match['path'],
                f'#{match["code"]}',
                match['message'],
                source_root,
                build_dir,
            )
            continue

        match = _GFORTRAN_LOCATION.match(line)
        if match is not None:
            location = match['path']
            continue

        match = _GFORTRAN_WARNING.match(line)
        if match is not None and location is not None:
            yield _make(
                location,
                match['flag'] or '',
                match['message'],
                source_root,
                build_dir,
            )
            location = None
            continue

        match = _CMAKE.match(line)
        if match is not None:
            cmake_path = match['path']


def _make(path, flag, message, source_root, build_dir):
    return BuildWarning(
        path=_relative(path, source_root, build_dir),
        flag=flag,
        message=_replace_roots(message, source_root, build_dir),
    )


def _relative(path, source_root, build_dir):
    path = os.path.normpath(path)
    for root, prefix in [(build_dir, '<build>/'), (source_root, '')]:
        if root is None:
            continue
        root = os.path.normpath(root)
        if path.startswith(root + os.sep):
            return prefix + os.path.relpath(path, root)
    return path


def _replace_roots(message, source_root, build_dir):
    for root, name in [(build_dir, '<build>'), (source_root, '<omega>')]:
        if root:
            message = message.replace(os.path.normpath(root), name)
    return message
