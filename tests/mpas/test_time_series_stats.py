import numpy as np
import xarray as xr

from polaris.mpas.time_series_stats import read_time_series


def _write_month(path, month, with_tendency=True):
    """Write one month of monthly means of two cells and two levels"""
    ds = xr.Dataset()
    ds['xtime_startMonthly'] = xr.DataArray(
        np.array([f'0001-{month:02d}-01_00:00:00'], dtype='S64'), dims='Time'
    )
    ds['timeMonthly_avg_ssh'] = xr.DataArray(
        [[month, -month]], dims=('Time', 'nCells')
    ).astype(float)
    ds['timeMonthly_avg_activeTracers_temperature'] = xr.DataArray(
        np.full((1, 2, 2), float(month)),
        dims=('Time', 'nCells', 'nVertLevels'),
    )
    ds['timeMonthly_avg_normalVelocity'] = xr.DataArray(
        np.zeros((1, 3, 2)), dims=('Time', 'nEdges', 'nVertLevels')
    )
    if with_tendency:
        ds['timeMonthly_avg_frazilLayerThicknessTendency'] = xr.DataArray(
            np.ones((1, 2, 2)), dims=('Time', 'nCells', 'nVertLevels')
        )
    ds['velocityTidalRMS'] = xr.DataArray([0.0, 0.0], dims='nCells')
    ds.to_netcdf(path)


def test_a_series_of_monthly_means_reads_only_the_fields_named(tmp_path):
    """More files than xarray keeps open give the named fields, renamed, in
    order, with the times of the means; a field a file lacks is NaN there,
    as when the files are opened together"""
    filenames = [str(tmp_path / f'means.0001-{m:02d}.nc') for m in range(1, 5)]
    for month, filename in enumerate(filenames, start=1):
        _write_month(filename, month, with_tendency=month < 3)

    with xr.set_options(file_cache_maxsize=2):
        ds = read_time_series(
            filenames,
            ['ssh', 'temperature', 'frazilLayerThicknessTendency'],
            prefix='timeMonthly_avg_',
        )

    assert sorted(ds.data_vars) == [
        'frazilLayerThicknessTendency',
        'ssh',
        'temperature',
        'xtime_startMonthly',
    ]
    np.testing.assert_array_equal(ds.ssh.isel(nCells=0), [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_array_equal(
        ds.frazilLayerThicknessTendency.isel(nCells=0, nVertLevels=0),
        [1.0, 1.0, np.nan, np.nan],
    )
    assert ds.xtime_startMonthly.values[3].decode().startswith('0001-04')
