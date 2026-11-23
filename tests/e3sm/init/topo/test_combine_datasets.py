"""
Unit tests for the choice of Antarctic dataset in combined topography and
for the firn air content subtracted from Bedmap3's thickness.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine import get_lat_lon_topo_steps
from polaris.tasks.e3sm.init.topo.combine.files import (
    ANTARCTIC_DATASETS,
    get_combine_files,
)
from polaris.tasks.e3sm.init.topo.combine.prepare import (
    interp_firn_air_content,
)


def _write_firn(path, firn):
    """A BedMachine-like file with firn on a 500 m grid with y descending"""
    ny, nx = firn.shape
    x = 500 * np.arange(nx)
    y = 500 * np.arange(ny)[::-1]
    ds = xr.Dataset(
        {'firn': (('y', 'x'), firn.astype(np.float32))},
        coords={'x': x, 'y': y},
    )
    ds.to_netcdf(path)
    return x, y


def test_firn_at_cell_corners_is_the_mean_of_the_four_cells(tmp_path):
    """
    Bedmap3's cell centers fall on BedMachine's cell corners, so bilinear
    interpolation is the mean of the four BedMachine cells around each one.
    """
    rng = np.random.default_rng(0)
    firn = rng.uniform(0.0, 30.0, size=(5, 6))
    filename = tmp_path / 'firn.nc'
    x, y = _write_firn(filename, firn)

    x_corner = xr.DataArray(x[:-1] + 250.0, dims='x')
    y_corner = xr.DataArray(y[:-1] - 250.0, dims='y')
    result = interp_firn_air_content(filename, x=x_corner, y=y_corner)

    expected = 0.25 * (
        firn[:-1, :-1] + firn[1:, :-1] + firn[:-1, 1:] + firn[1:, 1:]
    )
    assert result.dims == ('y', 'x')
    np.testing.assert_allclose(result.values, expected, rtol=1e-6)


def test_firn_outside_the_grid_or_missing_is_zero(tmp_path):
    """
    Bedmap3's outermost cells lie outside BedMachine's grid; there and where
    firn is missing, nothing should be subtracted rather than NaN spreading
    into the thickness.
    """
    firn = np.full((3, 3), 10.0)
    firn[1, 1] = np.nan
    filename = tmp_path / 'firn.nc'
    x, y = _write_firn(filename, firn)

    x_out = xr.DataArray([x[0] - 250.0, x[1]], dims='x')
    y_out = xr.DataArray([y[1]], dims='y')
    result = interp_firn_air_content(filename, x=x_out, y=y_out)

    assert result.values[0, 0] == 0.0
    assert result.values[0, 1] == 0.0


def _combine_config(antarctic_dataset):
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.e3sm.init.topo.combine', 'combine.cfg'
    )
    config.set('combine_topo', 'antarctic_dataset', antarctic_dataset)
    config.set('combine_topo', 'target_grid', 'lat_lon')
    config.set('combine_topo', 'resolution_latlon', '1.0')
    return config


@pytest.mark.parametrize('antarctic_dataset', ANTARCTIC_DATASETS)
def test_combine_files_follow_the_antarctic_dataset(antarctic_dataset):
    files = get_combine_files(_combine_config(antarctic_dataset))

    assert files.antarctic == antarctic_dataset
    assert files.combined.startswith(f'{antarctic_dataset}_')


def test_unknown_antarctic_dataset_is_an_error():
    with pytest.raises(ValueError, match='antarctic dataset'):
        get_combine_files(_combine_config('bedmap2'))


def test_each_antarctic_dataset_gets_its_own_shared_steps():
    """
    The dataset is part of the shared steps' paths and of their config, so
    combined topography from two datasets never lands in the same directory
    or in the same cached file.
    """
    steps = {}
    configs = {}
    for antarctic_dataset in ANTARCTIC_DATASETS:
        steps[antarctic_dataset], configs[antarctic_dataset] = (
            get_lat_lon_topo_steps(
                component=e3sm_init,
                resolution=1.0,
                antarctic_dataset=antarctic_dataset,
            )
        )

    subdirs = [
        {step.subdir for step in dataset_steps.values()}
        for dataset_steps in steps.values()
    ]
    assert not set.intersection(*subdirs)
    for antarctic_dataset, config in configs.items():
        assert (
            config.get('combine_topo', 'antarctic_dataset')
            == antarctic_dataset
        )
        for step in steps[antarctic_dataset].values():
            assert antarctic_dataset in step.subdir
