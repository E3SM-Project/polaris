"""
Reducing a run one year at a time: the years in parallel, and a cache of
each year's reduced values that later analyses of the run reuse
"""

import hashlib
import importlib
import json
import multiprocessing
import os
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version

import xarray as xr

#: The modules whose code reduces a year, so a change to any of them makes
#: the cached years stale
REDUCING_MODULES = [
    'polaris.tasks.e3sm.analysis.misomip.diagnostics',
    'polaris.tasks.e3sm.analysis.misomip.health',
    'polaris.ocean.ice_shelf.diagnostics',
    'polaris.ocean.overturning',
    'polaris.landice.diagnostics',
    'polaris.mpas.time_series_stats',
    'polaris.e3sm.analysis.calendar',
    'polaris.constants',
]

#: The packages whose versions the cached years depend on
REDUCING_PACKAGES = ['numpy', 'xarray', 'scipy', 'mpas_tools']

#: The name of the file describing a cached year
MANIFEST_FILENAME = 'manifest.json'


def map_years(function, items, processes):
    """
    Apply a function to each year's inputs, in parallel processes

    Parameters
    ----------
    function : callable
        A function defined at the top level of a module, taking one item
        and returning picklable results

    items : list
        The picklable inputs, one for each year

    processes : int
        The most processes to use; one reduces the years in this process

    Returns
    -------
    results : list
        The results, in the order of the items
    """
    processes = min(processes, len(items))
    if processes <= 1:
        return [function(item) for item in items]
    # the server imports the function's module once, and each worker forks
    # from it, rather than importing all of polaris's tasks itself
    context = multiprocessing.get_context('forkserver')
    context.set_forkserver_preload(['__main__', function.__module__])
    with ProcessPoolExecutor(
        max_workers=processes, mp_context=context
    ) as executor:
        return list(executor.map(function, items))


def get_cache_key(filenames, options):
    """
    The key of a year's reduced values: the code and packages that reduce
    it, the options it is reduced with and the files it is reduced from

    Parameters
    ----------
    filenames : list of str
        Every file the year is reduced from, including the initial condition
        and mesh

    options : dict
        The options the year is reduced with, as values JSON can hold

    Returns
    -------
    key : dict
        The key, which a cached year's manifest must match
    """
    code = hashlib.sha256()
    for name in REDUCING_MODULES:
        module = importlib.import_module(name)
        filename = module.__file__
        assert filename is not None
        with open(filename, 'rb') as module_file:
            code.update(module_file.read())
    files = []
    for filename in filenames:
        stat = os.stat(filename)
        files.append(
            [os.path.basename(filename), stat.st_size, stat.st_mtime_ns]
        )
    return dict(
        code=code.hexdigest(),
        packages={name: version(name) for name in REDUCING_PACKAGES},
        options=options,
        files=files,
    )


def read_cached_year(year_dir, key):
    """
    Read a year's reduced values from the cache, if they were reduced with
    the same key

    Parameters
    ----------
    year_dir : str
        The year's directory in the cache

    key : dict
        The year's key from :py:func:`get_cache_key`

    Returns
    -------
    datasets : dict of str to xarray.Dataset or None
        The year's reduced values, or ``None`` if the cache has none with
        this key
    """
    manifest = os.path.join(year_dir, MANIFEST_FILENAME)
    if not os.path.exists(manifest):
        return None
    with open(manifest) as manifest_file:
        cached = json.load(manifest_file)
    if cached['key'] != json.loads(json.dumps(key)):
        return None
    datasets = dict()
    for name in cached['datasets']:
        filename = os.path.join(year_dir, f'{name}.nc')
        with xr.open_dataset(filename, decode_times=False) as ds:
            datasets[name] = ds.load()
    return datasets


def write_cached_year(year_dir, key, datasets):
    """
    Write a year's reduced values to the cache, replacing any there

    The year is written to a temporary directory beside its own and then
    renamed, so a job that stops part way leaves no partial year.

    Parameters
    ----------
    year_dir : str
        The year's directory in the cache

    key : dict
        The year's key from :py:func:`get_cache_key`

    datasets : dict of str to xarray.Dataset
        The year's reduced values
    """
    parent = os.path.dirname(year_dir)
    os.makedirs(parent, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=parent, prefix='.partial_')
    for name, ds in datasets.items():
        # xarray's own encoding reads back exactly as written
        ds.to_netcdf(os.path.join(temp_dir, f'{name}.nc'))
    with open(os.path.join(temp_dir, MANIFEST_FILENAME), 'w') as manifest:
        json.dump(dict(key=key, datasets=sorted(datasets)), manifest)
    if os.path.exists(year_dir):
        shutil.rmtree(year_dir)
    os.rename(temp_dir, year_dir)
