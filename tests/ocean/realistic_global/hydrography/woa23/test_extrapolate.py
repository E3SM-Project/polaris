import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    extrapolate,
)

ExtrapolateStep = extrapolate.ExtrapolateStep

THRESHOLD = 0.01


def test_extrap_with_halo_wraps_in_longitude():
    """A value at the first longitude reaches the last one, not the middle."""
    field = np.zeros((3, 6))
    field[1, 0] = 1.0
    valid = field > 0.0
    nlon = field.shape[1]

    result = extrapolate._extrap_with_halo(
        field=field,
        kernel=ExtrapolateStep._get_kernel(),
        valid=valid,
        lon_with_halo=np.array(
            [nlon - 2, nlon - 1] + list(range(nlon)) + [0, 1]
        ),
        lon_no_halo=list(range(2, nlon + 2)),
    )

    assert result.shape == field.shape
    assert result[1, nlon - 1] > 0.0
    assert result[1, 1] > 0.0
    assert result[1, 3] == 0.0


def test_extrap_level_fills_ocean_but_not_land():
    """Missing ocean cells are filled; missing land cells stay missing."""
    ct = np.full((5, 8), 2.0)
    ct[1:4, 2:5] = np.nan
    ocean_mask = np.ones(ct.shape, dtype=bool)
    ocean_mask[2, 3] = False
    ds_level = _level_dataset(ct)

    ds_level = ExtrapolateStep._extrap_level(
        ds_level=ds_level, ocean_mask=ocean_mask, threshold=THRESHOLD
    )

    ct_out = ds_level.ct_an.values
    sa_out = ds_level.sa_an.values
    assert np.isnan(ct_out[2, 3])
    assert np.isnan(sa_out[2, 3])
    filled = ocean_mask & np.isnan(ct)
    # a uniform field extrapolates to the same uniform value
    assert ct_out[filled] == pytest.approx(2.0)
    assert sa_out[filled] == pytest.approx(35.0)
    assert ct_out[~np.isnan(ct)] == pytest.approx(2.0)


def test_extrap_level_without_mask_fills_everything():
    """Without an ocean mask, one valid cell is spread over the whole level."""
    ct = np.full((4, 6), np.nan)
    ct[0, 0] = 3.0
    ds_level = _level_dataset(ct)

    ds_level = ExtrapolateStep._extrap_level(
        ds_level=ds_level, ocean_mask=None, threshold=THRESHOLD
    )

    assert np.all(np.isfinite(ds_level.ct_an.values))
    assert ds_level.ct_an.values == pytest.approx(3.0)


@pytest.mark.parametrize('use_ocean_mask', [True, False])
def test_extrap_vert_fills_downward(tmp_path, monkeypatch, use_ocean_mask):
    """
    Missing values take the value above them, down through several levels,
    and only within the ocean mask when one is used.
    """
    monkeypatch.chdir(tmp_path)
    ct = np.array(
        [
            [[1.0, 2.0]],
            [[np.nan, np.nan]],
            [[np.nan, np.nan]],
        ]
    )
    ocean_mask = np.array(
        [
            [[1, 1]],
            [[1, 0]],
            [[1, 0]],
        ],
        dtype=np.int8,
    )
    dims = ('depth', 'lat', 'lon')
    xr.Dataset({'ct_an': (dims, ct), 'sa_an': (dims, ct + 33.0)}).to_netcdf(
        'in.nc'
    )
    xr.Dataset({'ocean_mask': (dims, ocean_mask)}).to_netcdf('ocean_mask.nc')

    step = object.__new__(ExtrapolateStep)
    step._extrap_vert(
        in_filename='in.nc',
        out_filename='out.nc',
        use_ocean_mask=use_ocean_mask,
    )

    with xr.open_dataset('out.nc') as ds_out:
        ct_out = ds_out.ct_an.values
        sa_out = ds_out.sa_an.values
    assert ct_out[:, 0, 0] == pytest.approx([1.0, 1.0, 1.0])
    assert sa_out[:, 0, 0] == pytest.approx([34.0, 34.0, 34.0])
    if use_ocean_mask:
        assert np.all(np.isnan(ct_out[1:, 0, 1]))
    else:
        assert ct_out[:, 0, 1] == pytest.approx([2.0, 2.0, 2.0])


def test_make_3d_ocean_mask(tmp_path, monkeypatch):
    """
    A level is ocean where its top is no deeper than the seafloor and the
    2D ocean mask is set.
    """
    monkeypatch.chdir(tmp_path)
    depth_bnds = np.array([[0.0, 100.0], [100.0, 200.0], [200.0, 300.0]])
    ds_woa = xr.Dataset(
        {
            'lon': ('lon', [0.0, 1.0]),
            'lon_bnds': (('lon', 'nbounds'), [[-0.5, 0.5], [0.5, 1.5]]),
            'lat': ('lat', [0.0]),
            'lat_bnds': (('lat', 'nbounds'), [[-0.5, 0.5]]),
            'depth': ('depth', depth_bnds.mean(axis=1)),
            'depth_bnds': (('depth', 'nbounds'), depth_bnds),
        }
    )
    ds_woa.to_netcdf('woa.nc')
    ds_topo = xr.Dataset(
        {
            'base_elevation': (('lat', 'lon'), [[-150.0, -150.0]]),
            'ocean_mask': (('lat', 'lon'), [[1.0, 0.0]]),
        }
    )
    ds_topo.to_netcdf('topography.nc')

    ExtrapolateStep._make_3d_ocean_mask()

    with xr.open_dataset('ocean_mask.nc') as ds_mask:
        mask = ds_mask.ocean_mask
        assert mask.dims == ('depth', 'lat', 'lon')
        assert mask.values[:, 0, 0].tolist() == [1, 1, 0]
        assert mask.values[:, 0, 1].tolist() == [0, 0, 0]


def _level_dataset(ct):
    """Return a single-depth WOA dataset with uniform salinity where valid."""
    sa = np.where(np.isfinite(ct), 35.0, np.nan)
    dims = ('lat', 'lon')
    return xr.Dataset({'ct_an': (dims, ct.copy()), 'sa_an': (dims, sa)})
