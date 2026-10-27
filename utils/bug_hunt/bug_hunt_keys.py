"""
Keys that identify a failure, so that the same failure on several rows or
nights is one finding, and helpers that read the phase and message of a
failure from test output
"""

import re
from typing import Optional, Tuple

#: a CIME test name: type and modifiers, grid, compset, then optionally
#: machine_compiler and test mods
_CIME_TEST = re.compile(
    r'^(?P<type>[A-Z]{2,}[A-Za-z0-9_]*)\.(?P<grid>[^.]+)\.(?P<compset>[^.]+)'
    r'(?:\.(?P<machine>[a-z][\w-]*_[\w-]+))?(?P<mods>(?:\.[^.]+)*)$'
)

#: a CIME phase reported as failed in a test's log
_CIME_PHASE_FAILED = re.compile(r'\b(?P<phase>[A-Z][A-Z_]+) FAILED for test\b')

#: the two runs a CIME comparison compared
_CIME_SUFFIXES = re.compile(
    r"compared suffixes suffix1 '(?P<one>\w+)' suffix2 '(?P<two>\w+)'"
)

#: a file in a source tree, as opposed to a test name or task path
_CODE_FILE = re.compile(
    r'\.(?:c|cc|cpp|cxx|h|hh|hpp|inc|f|f90|F90|py|cmake|yaml|yml|cfg|'
    r'sh|template|json|xml|txt|md)$'
)

#: lines that usually carry the first error in a log
_ERROR_LINE = re.compile(
    r'(error|exception|abort|segmentation fault|nan|fail)', re.IGNORECASE
)

#: lines that MPI and job launchers print around any abort, which say
#: nothing about its cause, and property checks that passed
_NOISE = re.compile(
    r'(mpich error|mpi_abort|aborting job|abort_on_error|srun: error|'
    r'cancelled at|segmentation fault|core dumped|exited with exit code|'
    r'\[pass\])',
    re.IGNORECASE,
)

#: a CIME run that failed outright
_CIME_RUN_FAIL = re.compile(r'\bRUN FAIL\b')

#: timestamps, which would otherwise make each run's message unique
_TIMESTAMP = re.compile(
    r'(\b(?:mon|tue|wed|thu|fri|sat|sun)\s+(?:jan|feb|mar|apr|may|jun|'
    r'jul|aug|sep|oct|nov|dec)\s+\d+\s+[\d:]+\s+\d{4}\b|'
    r'\b\d{4}-\d{2}-\d{2}[t ][\d:.]+)',
    re.IGNORECASE,
)

_HEX = re.compile(r'0x[0-9a-fA-F]+')
_PATH = re.compile(r'(?:[\w.~-]*/)+[\w.-]+')
_NUMBER = re.compile(r'[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?')
_SPACE = re.compile(r'\s+')

#: the longest a normalized message is kept
MESSAGE_LENGTH = 120

#: how CIME phases map to the phases of a key; ``COMPARE_*`` phases map to
#: ``compare``
CIME_PHASES = {
    'CREATE_NEWCASE': 'setup',
    'XML': 'setup',
    'SETUP': 'setup',
    'SHAREDLIB_BUILD': 'build',
    'MODEL_BUILD': 'build',
    'SUBMIT': 'setup',
    'RUN': 'run',
    'MEMLEAK': 'run',
    'BASELINE': 'baseline',
    'GENERATE': 'baseline',
    'TPUTCOMP': 'baseline',
    'MEMCOMP': 'baseline',
}


def normalize_test(name: str) -> str:
    """
    A test's name without the machine and compiler that some names carry

    CIME test names end with ``.<machine>_<compiler>`` and any test mods,
    such as ``PEM_Vmct.T62_oQU240.GOMEGA-IAF.pm-cpu_gnu`` or
    ``...GOMEGA-JRA1p5.pm-cpu_gnu.omega-jra_1958``.  Other names, such as
    CTest names and Polaris task paths, are returned unchanged.

    Parameters
    ----------
    name : str
        The test's name as it was reported

    Returns
    -------
    name : str
        The name with any machine and compiler removed
    """
    match = _CIME_TEST.match(name.strip())
    if match is None or match.group('machine') is None:
        return name.strip()
    return (
        f'{match.group("type")}.{match.group("grid")}.'
        f'{match.group("compset")}{match.group("mods")}'
    )


def is_cime_test(name: str) -> bool:
    """Whether a test name looks like a CIME test with its machine"""
    match = _CIME_TEST.match(name.strip())
    return match is not None and match.group('machine') is not None


def is_cime_name(name: str) -> bool:
    """Whether a name looks like a CIME test, with or without its machine"""
    return _CIME_TEST.match(name.strip()) is not None


def normalize_message(message: Optional[str]) -> Optional[str]:
    """
    A message with the parts that change from run to run removed

    Hexadecimal addresses, paths and numbers are replaced with placeholders,
    so that line numbers, ranks, timings and work directories do not make
    the same error look new.

    Parameters
    ----------
    message : str, optional
        The message as it was reported

    Returns
    -------
    message : str, optional
        The normalized message, in lower case, or ``None`` if there was none
    """
    if message is None:
        return None
    text = _TIMESTAMP.sub('<time>', message)
    text = _HEX.sub('<addr>', text)
    text = _PATH.sub('<path>', text)
    text = _NUMBER.sub('<n>', text)
    text = _SPACE.sub(' ', text).strip().lower()
    if not text:
        return None
    return text[:MESSAGE_LENGTH]


def cime_phase_and_message(
    output: Optional[str],
) -> Tuple[str, Optional[str]]:
    """
    The phase of a failed CIME test and a short message, from its log

    Parameters
    ----------
    output : str, optional
        The test's log, as CDash keeps it

    Returns
    -------
    phase : str
        ``setup``, ``build``, ``run`` or ``compare``

    message : str, optional
        A short description of the failure
    """
    if not output:
        return 'run', None
    match = _CIME_PHASE_FAILED.search(output)
    if match is not None:
        cime_phase = match.group('phase')
        return cime_phase_to_key(cime_phase), f'{cime_phase} failed'
    if 'did NOT match' in output:
        suffixes = _CIME_SUFFIXES.search(output)
        if suffixes is None:
            return 'compare', 'history files did not match'
        return 'compare', (
            f'{suffixes.group("one")} and {suffixes.group("two")} history '
            f'files did not match'
        )
    if _CIME_RUN_FAIL.search(output):
        return 'run', 'RUN failed'
    return 'run', None


def cime_phase_to_key(cime_phase: str) -> str:
    """
    The phase of a key for a CIME phase, such as ``compare`` for
    ``COMPARE_base_rest``

    Parameters
    ----------
    cime_phase : str
        The phase as CIME reports it

    Returns
    -------
    phase : str
        ``setup``, ``build``, ``run``, ``compare`` or ``baseline``
    """
    if cime_phase.startswith('COMPARE'):
        return 'compare'
    if cime_phase in CIME_PHASES:
        return CIME_PHASES[cime_phase]
    return CIME_PHASES.get(cime_phase.split('_')[0], 'run')


def first_error_line(output: Optional[str]) -> Optional[str]:
    """
    The first line of a log that looks like an error

    Lines that MPI and job launchers print around any abort are skipped,
    unless there is nothing else.

    Parameters
    ----------
    output : str, optional
        The log

    Returns
    -------
    line : str, optional
        The line, stripped, or ``None`` if no line looks like an error
    """
    if not output:
        return None
    fallback = None
    for line in output.splitlines():
        if not _ERROR_LINE.search(line):
            continue
        if _NOISE.search(line):
            if fallback is None:
                fallback = line.strip()[:MESSAGE_LENGTH]
            continue
        return line.strip()[:MESSAGE_LENGTH]
    return fallback


def location_key(where: str) -> Tuple[str, str]:
    """
    The test and phase of a key for a finding at a location in code or at
    a test

    Parameters
    ----------
    where : str
        A file with an optional line number (``src/ocn/Foo.cpp:123``), or
        the name of a test

    Returns
    -------
    test : str
        The file without its line number, or the normalized test name

    phase : str
        ``code`` for a file, or ``run`` for a test
    """
    where = where.strip()
    path, _, line = where.rpartition(':')
    if path and line.isdigit():
        where = path
    if _CIME_TEST.match(where) is None and _CODE_FILE.search(where):
        return where, 'code'
    return normalize_test(where), 'run'
