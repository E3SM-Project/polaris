import logging

import numpy as np
import xarray as xr

from polaris.validate import compare_variables


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
