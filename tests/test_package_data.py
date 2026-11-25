"""
Tests that every data file in the polaris package is installed with it.

setuptools installs only the non-Python files that
``[tool.setuptools.package-data]`` in ``pyproject.toml`` names, so a file of
a new kind is silently left out of a conda or pip package even though it
works from a development checkout.
"""

import fnmatch
import os
import subprocess
import tomllib

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYPROJECT = os.path.join(_ROOT, 'pyproject.toml')


def test_every_data_file_in_the_package_is_installed():
    if not os.path.exists(_PYPROJECT):
        pytest.skip('not run from a polaris checkout')
    patterns = _package_data_patterns()
    missing = [
        filename
        for filename in _package_files()
        if not filename.endswith('.py')
        and not any(
            fnmatch.fnmatch(os.path.basename(filename), pattern)
            for pattern in patterns
        )
    ]
    assert not missing, (
        f'[tool.setuptools.package-data] in pyproject.toml does not include '
        f'these files, so they would not be installed: {", ".join(missing)}'
    )


def _package_data_patterns():
    """
    The file-name patterns of polaris's package data, each of which applies
    in every directory of the package
    """
    with open(_PYPROJECT, 'rb') as data:
        pyproject = tomllib.load(data)
    patterns = pyproject['tool']['setuptools']['package-data']['polaris']
    for pattern in patterns:
        assert pattern.startswith('**/') and '/' not in pattern[3:], (
            f'Expected package data to be given as "**/<file name pattern>", '
            f'not {pattern!r}, so this test can check it'
        )
    return [pattern[3:] for pattern in patterns]


def _package_files():
    """The files of the polaris package that git tracks"""
    try:
        output = subprocess.run(
            ['git', 'ls-files', 'polaris'],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('not run from a git checkout of polaris')
    return output.split()
