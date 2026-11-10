"""Fixtures shared by unit tests in more than one directory."""

import json
import os
import subprocess
import sys

import pytest

#: the variables that size the numerical thread pools
POOL_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')

# What the checks that need a fresh interpreter ask of one, in the order that
# keeps each of them meaningful.  They share a single interpreter because
# starting one costs as much as importing numpy, xarray and every task, far
# more than any of the checks.
_FRESH_IMPORTS = """
import json
import sys


def _threads():
    # the count the kernel keeps, which is the only one that sees threads a
    # C library started.  threading.enumerate() sees Python threads only and
    # reported 1 where this reported 129.
    with open('/proc/self/status') as handle:
        return int(handle.read().split('Threads:')[1].split()[0])


def _import(name):
    try:
        __import__(name)
    except Exception as error:
        return repr(error)
    return None


report = {}
report['polaris_error'] = _import('polaris')
report['polaris_threads'] = _threads()
# polaris.ocean.conservation has to come before anything that imports
# polaris.ocean.model, or a circular import between them goes unnoticed
report['ocean_model_preloaded'] = 'polaris.ocean.model' in sys.modules
report['conservation_error'] = _import('polaris.ocean.conservation')
report['cli_error'] = _import('polaris.__main__')
report['cli_threads'] = _threads()
print(json.dumps(report))
"""


@pytest.fixture(scope='session')
def fresh_interpreter():
    """
    What a fresh interpreter reports after importing Polaris.

    A test about what happens at import cannot ask the interpreter it runs
    in, because by then the imports have already happened.  This one imports
    ``polaris``, then ``polaris.ocean.conservation``, then the CLI, with the
    pool variables unset, and returns a dict with the error from each import
    (or ``None``) and the number of OS threads after ``polaris`` and after
    the CLI.
    """
    environ = {
        name: value
        for name, value in os.environ.items()
        if name not in POOL_VARIABLES
    }
    result = subprocess.run(
        [sys.executable, '-c', _FRESH_IMPORTS],
        capture_output=True,
        text=True,
        env=environ,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])
