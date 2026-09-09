"""
Tests for the properties that make the scheduler safe to fork from.

Only the forking thread survives a fork.  A lock held by any other thread at
that moment is held forever in the child, and the symptom is a step that
hangs rather than one that fails, which is the worst kind to chase.  So the
scheduler has to hold no thread but its own, and has to be able to say so.

These run a fresh interpreter rather than asking about this one, because
what is being tested is what happens at import, and by the time a test runs
the imports have already happened.
"""

import subprocess
import sys

# reads the count the kernel keeps, which is the only one that sees threads
# a C library started.  `threading.enumerate()` sees Python threads only and
# reported 1 where this reported 129.
COUNT_THREADS = (
    "print(open('/proc/self/status').read().split('Threads:')[1].split()[0])"
)


def _threads_after(statement, environ=None):
    """How many OS threads a fresh interpreter holds after running this."""
    result = subprocess.run(
        [sys.executable, '-c', f'{statement}; {COUNT_THREADS}'],
        capture_output=True,
        text=True,
        env=environ,
        check=True,
    )
    return int(result.stdout.strip())


def _clean_environ(**overrides):
    """An environment with the pool variables unset, plus any overrides."""
    import os

    environ = {
        name: value
        for name, value in os.environ.items()
        if name
        not in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')
    }
    environ.update(overrides)
    return environ


def test_importing_polaris_leaves_almost_no_threads():
    """
    The property the fork depends on, measured the way the kernel sees it.

    Without this, importing polaris leaves 129 threads on a 128-core node --
    an OpenBLAS pool numpy raises at import, one per visible core.
    """
    threads = _threads_after('import polaris', _clean_environ())

    assert threads <= 4, (
        f'importing polaris left {threads} OS threads, which is not safe to '
        f'fork from'
    )


def test_the_pools_are_pinned_before_numpy_is_imported():
    """
    Placement is the whole trick, and it is easy to get wrong.

    OpenBLAS sizes its pool when numpy is first imported, so pinning has to
    happen above the package's own imports.  Doing it in `polaris/__main__.py`
    was tried and is too late: importing that module imports the package
    first.
    """
    threads = _threads_after('import polaris.__main__', _clean_environ())

    assert threads <= 4, (
        f'the polaris CLI left {threads} OS threads; the pools are being '
        f'pinned after numpy has already built one'
    )


def test_a_deliberate_choice_still_wins():
    """Pinned by default, not imposed: a job script may say otherwise."""
    threads = _threads_after(
        'import polaris',
        _clean_environ(OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4'),
    )

    assert threads > 4, (
        f'OPENBLAS_NUM_THREADS=4 gave {threads} OS threads; the pin is '
        f'overriding a deliberate choice instead of defaulting'
    )
