import gsw
import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.global_ocean.hydrography.woa23.combine import (
    CombineStep,
)


def test_to_canonical_teos10():
    ds = xr.Dataset(
        data_vars={
            't_an': (
                ('depth', 'lat', 'lon'),
                np.array(
                    [
                        [[1.0, 2.0], [3.0, np.nan]],
                        [[0.5, 1.5], [2.5, 3.5]],
                    ]
                ),
            ),
            's_an': (
                ('depth', 'lat', 'lon'),
                np.array(
                    [
                        [[34.5, 34.7], [34.9, 35.1]],
                        [[34.6, 34.8], [35.0, np.nan]],
                    ]
                ),
            ),
        },
        coords={
            'depth': ('depth', np.array([0.0, 1000.0])),
            'lat': ('lat', np.array([-45.0, 10.0])),
            'lon': ('lon', np.array([20.0, 160.0])),
        },
    )

    ds_out = CombineStep._to_canonical_teos10(ds)

    assert 't_an' not in ds_out
    assert 's_an' not in ds_out
    assert ds_out.ct_an.attrs['standard_name'] == (
        'sea_water_conservative_temperature'
    )
    assert ds_out.sa_an.attrs['standard_name'] == (
        'sea_water_absolute_salinity'
    )
    assert ds_out.sa_an.attrs['units'] == 'g kg-1'

    expected_ct = np.full(ds_out.ct_an.shape, np.nan)
    expected_sa = np.full(ds_out.sa_an.shape, np.nan)
    for depth_index, depth in enumerate(ds.depth.values):
        temp = ds.t_an.isel(depth=depth_index).values
        practical_salinity = ds.s_an.isel(depth=depth_index).values
        level = ds.t_an.isel(depth=depth_index)
        lat = ds.lat.broadcast_like(level).values
        lon = ds.lon.broadcast_like(level).values
        pressure = gsw.p_from_z(-depth, lat)
        mask = np.isfinite(temp) & np.isfinite(practical_salinity)

        expected_sa[depth_index, :, :][mask] = gsw.SA_from_SP(
            practical_salinity[mask],
            pressure[mask],
            lon[mask],
            lat[mask],
        )
        expected_ct[depth_index, :, :][mask] = gsw.CT_from_t(
            expected_sa[depth_index, :, :][mask],
            temp[mask],
            pressure[mask],
        )

    assert ds_out.ct_an.values == pytest.approx(expected_ct, nan_ok=True)
    assert ds_out.sa_an.values == pytest.approx(expected_sa, nan_ok=True)
