"""
How much memory the process running a step holds.

`polaris serial` runs the steps of a suite one after another in a single
process, so whatever one step leaves behind is still held while every later
step runs.  The batch system reports one peak for the whole job, after the
fact, which says that memory grew but not where.  These are the numbers
recorded after each step so that growth can be traced to the step where it
happened.

On Linux they come from ``/proc/self/status``, and the peak is reset before
each step so that it describes that step alone.  Elsewhere only the peak
that ``getrusage()`` reports is available, which is the peak since the
process started.
"""

import resource
import sys
from dataclasses import dataclass
from typing import Optional

_STATUS = '/proc/self/status'
# writing 5 here resets the peak resident set size to the current one
# (Linux 4.0 and later)
_CLEAR_REFS = '/proc/self/clear_refs'


@dataclass(frozen=True)
class ProcessMemory:
    """
    The memory held by this process and its finished subprocesses.

    Attributes
    ----------
    resident : int or None
        The bytes this process holds now, or ``None`` where that cannot be
        read

    peak : int
        The most bytes this process has held since the peak was last reset,
        or since it started if the peak could not be reset

    largest_subprocess : int
        The most bytes held by any subprocess that has finished, over the
        life of this process
    """

    resident: Optional[int]
    peak: int
    largest_subprocess: int


def reset_peak_memory() -> bool:
    """
    Reset this process's peak memory to what it holds now.

    Returns
    -------
    reset : bool
        Whether the peak was reset.  Where it cannot be, the peak that
        :py:func:`read_process_memory` reports is the peak since the process
        started.
    """
    try:
        with open(_CLEAR_REFS, 'w') as handle:
            handle.write('5')
    except OSError:
        return False
    return True


def read_process_memory() -> ProcessMemory:
    """
    Read how much memory this process and its subprocesses have held.

    Returns
    -------
    memory : polaris.run.memory.ProcessMemory
        The memory this process holds now, its peak and the peak of its
        largest finished subprocess
    """
    status = _read_status()
    resident = status.get('VmRSS')
    peak = status.get('VmHWM')
    if peak is None:
        peak = _rusage_peak(resource.RUSAGE_SELF)
    largest_subprocess = _rusage_peak(resource.RUSAGE_CHILDREN)
    return ProcessMemory(
        resident=resident,
        peak=peak,
        largest_subprocess=largest_subprocess,
    )


def format_bytes(nbytes: Optional[int]) -> str:
    """
    Format a number of bytes for a log, in binary units.

    Parameters
    ----------
    nbytes : int or None
        The number of bytes, or ``None`` if it is not known

    Returns
    -------
    text : str
        The number with the largest unit that leaves it at least 1
    """
    if nbytes is None:
        return 'unknown'
    value = float(nbytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if value < 1024.0:
            return f'{value:.1f} {unit}'
        value /= 1024.0
    return f'{value:.1f} TiB'


def _read_status():
    """
    Read the resident and peak resident set sizes, in bytes, from the
    kernel's status for this process, or nothing where it has none.
    """
    sizes = {}
    try:
        with open(_STATUS) as handle:
            for line in handle:
                key, _, value = line.partition(':')
                if key in ('VmRSS', 'VmHWM'):
                    # reported in kB, which the kernel means as KiB
                    sizes[key] = int(value.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return {}
    return sizes


def _rusage_peak(who):
    """
    The peak resident set size ``getrusage()`` reports, in bytes.
    """
    peak = resource.getrusage(who).ru_maxrss
    # bytes on macOS, KiB everywhere else
    if sys.platform != 'darwin':
        peak *= 1024
    return peak
