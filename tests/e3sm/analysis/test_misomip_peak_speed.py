import numpy as np
import xarray as xr

from polaris.mpas.time_series_stats import read_time_series
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    CUSTOM_FIELDS,
    _cell_speed,
    _edge_speed,
)


def test_the_peak_speed_is_the_largest_anywhere(tmp_path):
    """Each record's largest edge speed, either sign, and each day's speed
    of the largest kinetic energy, leaving out the fill value below the
    seafloor"""
    ds_stats = xr.Dataset()
    ds_stats['xtime'] = (
        'Time',
        np.array(['0002-01-01_01:00:00', '0002-01-01_02:00:00'], dtype='S64'),
    )
    ds_stats['normalVelocityMax'] = ('Time', [1.0, 0.5])
    ds_stats['normalVelocityMin'] = ('Time', [-0.2, -2.0])
    ds_edge = _edge_speed(ds_stats)
    np.testing.assert_allclose(ds_edge.maxEdgeSpeed, [1.0, 2.0])
    np.testing.assert_allclose(
        ds_edge.recordTime, 365.0 + np.array([1, 2]) / 24
    )

    filename = str(tmp_path / 'custom.0002-01-01.nc')
    ds = xr.Dataset()
    ds['xtime_startCustom'] = (
        'Time',
        np.array(['0002-01-01_00:01:00', '0002-01-02_00:01:00'], dtype='S64'),
    )
    kinetic_energy = np.array(
        [[[0.5, 2.0], [1.0, 9.96921e36]], [[8.0, 0.0], [0.0, 9.96921e36]]],
        dtype=np.float32,
    )
    ds['timeCustom_max_kineticEnergyCell'] = (
        ('Time', 'nCells', 'nVertLevels'),
        kinetic_energy,
    )
    ds.timeCustom_max_kineticEnergyCell.encoding['_FillValue'] = np.float32(
        9.96921e36
    )
    ds.to_netcdf(filename)
    ds_cell = _cell_speed(read_time_series([filename], CUSTOM_FIELDS))
    np.testing.assert_allclose(ds_cell.dayStart, [365.0, 366.0])
    np.testing.assert_allclose(ds_cell.maxCellSpeed, [2.0, 4.0])
