"""
Guards on what Polaris imports, which is most of what a command costs

Each runs a fresh interpreter, because what is being tested is what happens
at import, and by the time a test runs the imports have already happened.
"""

import json
import subprocess
import sys

import pytest

# third-party packages that the framework core and the command modules must
# leave to the steps that use them
DEFERRED = [
    'numpy',
    'xarray',
    'scipy',
    'pandas',
    'matplotlib',
    'cartopy',
    'cmocean',
    'networkx',
    'igraph',
    'dask',
    'jigsawpy',
    'mpas_tools',
    'pyremap',
    'shapely',
    'netCDF4',
    'geometric_features',
    'mache',
    'jinja2',
    'ruamel',
]


@pytest.mark.parametrize(
    'module',
    [
        'polaris',
        'polaris.__main__',
        'polaris.list',
        'polaris.setup',
        'polaris.suite',
    ],
)
def test_importing_leaves_third_party_packages_unimported(module):
    imported = _imported_after(f'import {module}', DEFERRED)
    assert imported == [], (
        f'importing {module} imported {imported}; defer these with '
        f'polaris.lazy (see utils/defer_imports/defer_imports.py)'
    )


def test_building_one_task_group_leaves_plotting_unimported():
    """
    Setting up a task builds only its task group, and that must not import
    the packages that only plotting and mesh-masking steps use
    """
    statement = (
        'from polaris.tasks import get_components; '
        "get_components(task_groups={'ocean': ['baroclinic_channel']})"
    )
    plotting = ['matplotlib', 'cartopy', 'cmocean', 'networkx', 'igraph']
    imported = _imported_after(statement, plotting + ['dask'])
    assert imported == []


def test_polaris_list_reads_the_manifest_without_building_tasks():
    """With a fresh manifest, polaris list imports no task module"""
    # make sure the manifest is fresh
    _imported_after(
        'from polaris.tasks.manifest import get_manifest; get_manifest()', []
    )
    statement = (
        'import contextlib, io, sys\n'
        "sys.argv = ['polaris', 'list']\n"
        'from polaris.list import main\n'
        'with contextlib.redirect_stdout(io.StringIO()):\n'
        '    main()'
    )
    imported = _imported_after(
        statement, ['polaris.tasks.ocean', 'polaris.tasks.mesh']
    )
    assert imported == []


def _imported_after(statement, packages):
    """Which of the packages a fresh interpreter has imported after this"""
    code = (
        f'{statement}\n'
        'import json, sys\n'
        f'print(json.dumps([p for p in {packages!r} if p in sys.modules]))\n'
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])
