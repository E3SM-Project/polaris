import os

import numpy as np
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.years import (
    get_cache_key,
    map_years,
    read_cached_year,
    write_cached_year,
)


def test_years_reduced_in_processes_come_back_in_order():
    assert map_years(abs, [-1, -2, -3, -4], processes=2) == [1, 2, 3, 4]


def test_a_cached_year_is_reused_only_with_the_same_files_and_options(
    tmp_path,
):
    """A year reads back as it was written; a file rewritten since, or a
    different option, misses the cache"""
    source = tmp_path / 'means.0001-01-01.nc'
    source.write_text('one')
    year_dir = str(tmp_path / 'cache' / 'year_0001')
    ds = xr.Dataset({'meltRate': ('Time', np.array([1.0, np.nan, 3.0]))})
    key = get_cache_key([str(source)], dict(deep_draft=-300.0))

    write_cached_year(year_dir, key, dict(series=ds))

    cached = read_cached_year(year_dir, key)
    assert cached is not None
    xr.testing.assert_identical(cached['series'], ds)
    assert sorted(os.listdir(tmp_path / 'cache')) == ['year_0001']

    other_options = get_cache_key([str(source)], dict(deep_draft=-200.0))
    assert read_cached_year(year_dir, other_options) is None

    source.write_text('rewritten')
    os.utime(source, ns=(0, 0))
    assert read_cached_year(year_dir, get_cache_key([str(source)], {})) is None
