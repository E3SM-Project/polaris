import json
import logging

import numpy as np
import pytest
import xarray as xr

from polaris import Component, Step
from polaris.run.lifecycle import read_baseline_diff_summary_from_logs
from polaris.validate import compare_variables, merge_diff_summary


def _make_datasets(values1, values2):
    ds1 = xr.Dataset({'mask': ('nCells', np.array(values1))})
    ds2 = xr.Dataset({'mask': ('nCells', np.array(values2))})
    return ds1, ds2


def _compare(ds1, ds2, tmp_path):
    # the files have to exist but the datasets are passed in directly
    filename1 = str(tmp_path / 'file1.nc')
    filename2 = str(tmp_path / 'file2.nc')
    for filename in [filename1, filename2]:
        with open(filename, 'w'):
            pass
    return compare_variables(
        component=None,
        variables=['mask'],
        filename1=filename1,
        filename2=filename2,
        logger=logging.getLogger('test_validate'),
        config=None,
        ds1=ds1,
        ds2=ds2,
    )


def test_compare_variables_passes_for_identical_boolean_fields(tmp_path):
    # booleans don't support subtraction, so they have to be converted
    # before the norms are computed
    values = [True, False, True, True]
    ds1, ds2 = _make_datasets(values, values)
    assert ds1.mask.dtype == bool

    assert _compare(ds1, ds2, tmp_path)


def test_compare_variables_fails_for_differing_boolean_fields(tmp_path):
    ds1, ds2 = _make_datasets(
        [True, False, True, True], [True, False, False, True]
    )

    assert not _compare(ds1, ds2, tmp_path)


def test_float32_diff_summary_survives_write_read_and_merge(tmp_path):
    # norms of float32 fields are numpy float32 scalars, which used to be
    # written to the json file as strings and then fail to merge
    work_dir = tmp_path / 'work'
    baseline_dir = tmp_path / 'baseline'
    values = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    for directory, offset in [(work_dir, 0.5), (baseline_dir, 0.0)]:
        directory.mkdir()
        ds = xr.Dataset({'cellWidth': ('nCells', values + offset)})
        ds.to_netcdf(directory / 'output.nc')
    assert ds.cellWidth.dtype == np.float32

    step = Step(component=Component(name='mesh'), name='build', subdir='')
    step.work_dir = str(work_dir)
    step.baseline_dir = str(baseline_dir)
    step.validate_vars = {'output.nc': ['cellWidth']}
    step.logger = logging.getLogger('test_validate')

    compared, success = step.validate_baselines()
    assert compared and not success

    with open(work_dir / 'baseline_diff_summary.json') as handle:
        written = json.load(handle)
    assert written['cellWidth'] == pytest.approx(
        {'l1': 1.5, 'l2': 0.75**0.5, 'linf': 0.5}
    )

    # a task that reuses the step merges its summary with others
    overall: dict = {}
    for _ in range(2):
        merge_diff_summary(
            overall, read_baseline_diff_summary_from_logs(str(work_dir))
        )
    assert overall == written


def test_read_diff_summary_converts_string_norms(tmp_path):
    # summaries already on disk may hold norms written as strings
    summary = {'cellWidth': {'l1': '0.0', 'l2': '0.0', 'linf': '0.5'}}
    with open(tmp_path / 'baseline_diff_summary.json', 'w') as handle:
        json.dump(summary, handle)

    overall = {'cellWidth': {'l1': 0.0, 'l2': 0.0, 'linf': 0.25}}
    merge_diff_summary(
        overall, read_baseline_diff_summary_from_logs(str(tmp_path))
    )
    assert overall == {'cellWidth': {'l1': 0.0, 'l2': 0.0, 'linf': 0.5}}
