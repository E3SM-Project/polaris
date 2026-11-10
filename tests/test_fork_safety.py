"""
Tests for the properties that make the scheduler safe to fork from.

Only the forking thread survives a fork.  A lock held by any other thread at
that moment is held forever in the child, and the symptom is a step that
hangs rather than one that fails, which is the worst kind to chase.  So the
scheduler has to hold no thread but its own, and has to be able to say so.

The thread counts come from a fresh interpreter (the ``fresh_interpreter``
fixture) rather than this one, because what is being tested is what happens
at import, and by the time a test runs the imports have already happened.
"""

import importlib
import os

import polaris


def test_importing_polaris_leaves_almost_no_threads(fresh_interpreter):
    """
    The property the fork depends on, measured the way the kernel sees it.

    Without this, importing polaris leaves 129 threads on a 128-core node --
    an OpenBLAS pool numpy raises at import, one per visible core.
    """
    assert fresh_interpreter['polaris_error'] is None
    threads = fresh_interpreter['polaris_threads']

    assert threads <= 4, (
        f'importing polaris left {threads} OS threads, which is not safe to '
        f'fork from'
    )


def test_the_pools_are_pinned_before_numpy_is_imported(fresh_interpreter):
    """
    Placement is the whole trick, and it is easy to get wrong.

    OpenBLAS sizes its pool when numpy is first imported, so pinning has to
    happen above the package's own imports.  Doing it in `polaris/__main__.py`
    was tried and is too late: importing that module imports the package
    first.
    """
    assert fresh_interpreter['cli_error'] is None
    threads = fresh_interpreter['cli_threads']

    assert threads <= 4, (
        f'the polaris CLI left {threads} OS threads; the pools are being '
        f'pinned after numpy has already built one'
    )


def test_a_deliberate_choice_still_wins(monkeypatch):
    """
    Pinned by default, not imposed: a job script may say otherwise.

    This runs the package's pinning again against an environment that has
    chosen a size for one pool and left the others unset.
    """
    environ = {'OPENBLAS_NUM_THREADS': '4'}
    monkeypatch.setattr(os, 'environ', environ)
    importlib.reload(polaris)

    assert environ == {
        'OPENBLAS_NUM_THREADS': '4',
        'OMP_NUM_THREADS': '1',
        'MKL_NUM_THREADS': '1',
    }, (
        'the pin is overriding a deliberate choice instead of defaulting, '
        'or is not pinning the pools that were left unset'
    )
