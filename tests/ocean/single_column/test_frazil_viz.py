import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.single_column.mpas_ocean_frazil_viz import (
    MPAS_OCEAN_FRAZIL_ACCUMULATED,
    MPAS_OCEAN_FRAZIL_TENDENCIES,
    mpas_ocean_frazil_data,
)


@pytest.mark.parametrize(
    'hours, expected',
    [
        ([0, 6, 12, 24, 30, 48, 54], [24, 48, 54]),
        ([1, 23, 25, 47, 49], [23, 47, 49]),
        ([0, 0.1, 0.2], [0.2]),
        ([24], [24]),
        ([24, 72], [24, 72]),
        ([24 + 1e-12, 48 + 1e-12, 50], [24 + 1e-12, 48 + 1e-12, 50]),
    ],
)
def test_daily_frazil_profiles(hours, expected):
    time = np.asarray(hours)
    shape = (len(time), 2, 2)
    ds = xr.Dataset(
        {
            'daysSinceStartOfSim': ('Time', time / 24.0),
            'layerThickness': (
                ('Time', 'nCells', 'nVertLevels'),
                np.ones(shape),
            ),
            'zMid': (
                ('Time', 'nCells', 'nVertLevels'),
                np.broadcast_to([-0.5, -1.5], shape),
            ),
        }
    )
    for field in MPAS_OCEAN_FRAZIL_TENDENCIES:
        ds[field] = (
            ('Time', 'nCells', 'nVertLevels'),
            np.broadcast_to(time[:, None, None], shape),
        )
    for field in MPAS_OCEAN_FRAZIL_ACCUMULATED:
        ds[field] = (
            ('Time', 'nCells'),
            np.broadcast_to(time[:, None], (len(time), 2)),
        )
    mesh = xr.Dataset({'areaCell': ('nCells', [1.0, 2.0])})

    data = mpas_ocean_frazil_data(ds, mesh)

    np.testing.assert_allclose(data['profile_hours'], expected)
    for field in MPAS_OCEAN_FRAZIL_TENDENCIES:
        np.testing.assert_allclose(
            data['profiles'][field],
            np.broadcast_to(np.asarray(expected)[:, None], (len(expected), 2)),
        )
    for field in MPAS_OCEAN_FRAZIL_ACCUMULATED:
        np.testing.assert_allclose(data['accumulated'][field], time)
