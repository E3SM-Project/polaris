import numpy as np
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.ice_sheet import read_landice_history


def _write_year(path, year, thickness):
    """Write one year of history with two monthly records"""
    ds = xr.Dataset()
    ds['xtime'] = xr.DataArray(
        np.array(
            [f'{year:04d}-01-01_00:00:00', f'{year:04d}-02-01_00:00:00'],
            dtype='S64',
        ),
        dims='Time',
    )
    ds['thickness'] = xr.DataArray(
        np.full((2, 3), thickness), dims=('Time', 'nCells')
    )
    ds['velocity'] = xr.DataArray(np.zeros((2, 3)), dims=('Time', 'nCells'))
    ds.to_netcdf(path)


def test_yearly_history_files_read_as_one_series(tmp_path):
    """Two yearly files give one series of four records, in order, with
    only the fields that locate the grounding line"""
    filenames = [str(tmp_path / f'output.{year:05d}.nc') for year in [0, 1]]
    for year, filename in enumerate(filenames):
        _write_year(filename, year + 1, thickness=100.0 + year)
    ds = read_landice_history(filenames)
    assert ds.sizes['Time'] == 4
    assert ds.xtime.values[2].decode().startswith('0002-01-01')
    np.testing.assert_array_equal(
        ds.thickness.isel(nCells=0), [100.0, 100.0, 101.0, 101.0]
    )
    assert 'velocity' not in ds
