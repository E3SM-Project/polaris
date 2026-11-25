"""
Tests that the Quick Start for Users installs the JIGSAW polaris uses.

Users who install polaris from conda-forge have no ``jigsaw-python``
submodule, so the Quick Start names the commit to check out, and it has to
follow the submodule when the submodule is updated.
"""

import os
import subprocess

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_QUICK_START = os.path.join(_ROOT, 'docs', 'users_guide', 'quick_start.md')


def test_the_quick_start_checks_out_the_jigsaw_python_submodule():
    if not os.path.exists(_QUICK_START):
        pytest.skip('not run from a polaris checkout')
    commit = _submodule_commit('jigsaw-python')
    with open(_QUICK_START, encoding='utf-8') as quick_start:
        text = quick_start.read()
    assert f'git -C jigsaw-python checkout {commit}' in text, (
        f'docs/users_guide/quick_start.md should check out jigsaw-python '
        f'{commit}, the commit of the jigsaw-python submodule.'
    )


def _submodule_commit(path):
    """The commit a submodule points to in the git index"""
    try:
        output = subprocess.run(
            ['git', 'ls-files', '--stage', path],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('not run from a git checkout of polaris')
    if not output:
        pytest.skip(f'{path} is not a submodule of this checkout')
    # <mode> <commit> <stage>\t<path>
    return output.split()[1]
