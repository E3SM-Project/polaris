"""
Unit tests for the utility that converts MPAS initial conditions to the PCD
mean Earth radius.
"""

import importlib.util
from pathlib import Path

import netCDF4
import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant

COORD_RADIUS = 6371229.0


def test_rescales_from_coordinates_when_sphere_radius_is_wrong(tmp_path):
    utility = _load_utility()
    input_file = tmp_path / 'seaice.mesh.180705.nc'
    output_file = tmp_path / 'seaice.mesh.20261124.nc'
    ds_in = _make_mesh(sphere_radius=6371230.0)
    ds_in.to_netcdf(input_file, format='NETCDF4')

    utility.convert_ic(str(input_file), str(output_file))

    new_radius = float(get_constant('mean_radius'))
    ratio = new_radius / COORD_RADIUS
    with xr.open_dataset(output_file) as ds_out:
        assert ds_out.attrs['sphere_radius'] == new_radius
        assert 'was 6371230.0' in ds_out.attrs['history']
        for loc in ['Cell', 'Edge', 'Vertex']:
            np.testing.assert_allclose(
                _distance(ds_out, loc), new_radius, rtol=1e-14
            )
        np.testing.assert_allclose(
            ds_out['areaCell'], ratio**2 * ds_in['areaCell'], rtol=1e-14
        )
        assert 'fVertex' not in ds_out


@pytest.mark.parametrize(
    'xarray_format, file_format',
    [('NETCDF4', 'NETCDF4'), ('NETCDF3_64BIT', 'NETCDF3_64BIT_OFFSET')],
)
def test_keeps_an_unlimited_dimension_no_variable_uses(
    tmp_path, xarray_format, file_format
):
    utility = _load_utility()
    input_file = tmp_path / 'seaice.mesh.180705.nc'
    output_file = tmp_path / 'seaice.mesh.20261124.nc'
    _make_mesh(sphere_radius=COORD_RADIUS).to_netcdf(
        input_file, format=xarray_format
    )
    with netCDF4.Dataset(input_file, 'a') as nc:
        nc.createDimension('Time', None)

    utility.convert_ic(str(input_file), str(output_file))

    with netCDF4.Dataset(output_file) as nc:
        assert nc.data_model == file_format
        assert nc.dimensions['Time'].isunlimited()


def test_get_coordinate_radius_rejects_points_off_one_sphere():
    utility = _load_utility()
    ds = _make_mesh(sphere_radius=COORD_RADIUS)
    ds['xEdge'] = 1.001 * ds['xEdge']

    with pytest.raises(ValueError, match='not on one sphere'):
        utility.get_coordinate_radius(ds)


def _load_utility():
    module_path = (
        Path(__file__).resolve().parents[2]
        / 'utils'
        / 'mpas'
        / 'convert_ic_to_pcd_radius.py'
    )
    spec = importlib.util.spec_from_file_location(
        'convert_ic_to_pcd_radius', module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_mesh(sphere_radius):
    rng = np.random.default_rng(seed=0)
    sizes = {'Cell': 5, 'Edge': 7, 'Vertex': 4}
    ds = xr.Dataset(
        attrs={'on_a_sphere': 'YES', 'sphere_radius': sphere_radius}
    )
    for loc, size in sizes.items():
        points = rng.normal(size=(3, size))
        points *= COORD_RADIUS / np.linalg.norm(points, axis=0)
        for coord, values in zip('xyz', points, strict=True):
            ds[f'{coord}{loc}'] = ((f'n{loc}s',), values)
    for name in ['dcEdge', 'dvEdge']:
        ds[name] = (('nEdges',), rng.uniform(1.0e5, 2.0e5, sizes['Edge']))
    ds['areaCell'] = (('nCells',), rng.uniform(1.0e10, 2.0e10, sizes['Cell']))
    ds['areaTriangle'] = (
        ('nVertices',),
        rng.uniform(1.0e10, 2.0e10, sizes['Vertex']),
    )
    ds['kiteAreasOnVertex'] = (
        ('nVertices', 'vertexDegree'),
        rng.uniform(1.0e9, 2.0e9, (sizes['Vertex'], 3)),
    )
    ds['fVertex'] = (('nVertices',), rng.uniform(-1e-4, 1e-4, sizes['Vertex']))
    return ds


def _distance(ds, loc):
    return np.sqrt(
        ds[f'x{loc}'] ** 2 + ds[f'y{loc}'] ** 2 + ds[f'z{loc}'] ** 2
    )
