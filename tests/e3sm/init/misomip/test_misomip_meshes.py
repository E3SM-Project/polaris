import numpy as np
import pyproj
import pytest
import xarray as xr
from mpas_tools.mesh.conversion import cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.partitions import get_core_list
from polaris.tasks.e3sm.init.misomip import MESH_PAIRS, get_misomip_mesh_steps
from polaris.tasks.e3sm.init.misomip.names import get_grid_names
from polaris.tasks.e3sm.init.misomip.projection import (
    SPHERE_RADIUS,
    add_lat_lon,
    get_lat_lon,
    get_projection_string,
)
from polaris.tasks.e3sm.init.misomip.scrip import (
    clip_polygon_to_y_band,
    write_scrip,
)


def _great_circle_distance(lat0, lon0, lat1, lon1):
    """The distance in m along the sphere between two points"""
    cos_angle = np.sin(lat0) * np.sin(lat1) + np.cos(lat0) * np.cos(
        lat1
    ) * np.cos(lon1 - lon0)
    return SPHERE_RADIUS * np.arccos(np.clip(cos_angle, -1.0, 1.0))


def _to_planar(lat, lon):
    """The protocols' planar coordinates from latitude and longitude"""
    transformer = pyproj.Transformer.from_proj(
        pyproj.Proj(f'+proj=longlat +R={SPHERE_RADIUS:.0f}'),
        pyproj.Proj(get_projection_string()),
    )
    return transformer.transform(np.rad2deg(lon), np.rad2deg(lat))


def _polygon_area(x, y):
    """The area of a planar polygon by the shoelace formula"""
    return 0.5 * np.abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def test_projection_center():
    lat, lon = get_lat_lon(np.array([560.0e3]), np.array([40.0e3]))
    assert np.rad2deg(lat[0]) == pytest.approx(-75.0, abs=1e-10)
    assert np.mod(np.rad2deg(lon[0]) + 180.0, 360.0) - 180.0 == pytest.approx(
        0.0, abs=1e-10
    )


def test_projection_orientation():
    # x points north
    lat, lon = get_lat_lon(np.array([560.0e3, 660.0e3]), np.array([40e3] * 2))
    assert lat[1] > lat[0]
    assert lon[1] == pytest.approx(lon[0], abs=1e-12)

    # y points west
    lat, lon = get_lat_lon(np.array([560.0e3] * 2), np.array([40e3, 80e3]))
    dlon = np.mod(lon[1] - lon[0] + np.pi, 2.0 * np.pi) - np.pi
    assert dlon < 0.0

    # longitudes are between 0 and 2 pi
    assert np.all(lon >= 0.0) and np.all(lon < 2.0 * np.pi)


def test_projection_scale():
    dx = 1.0e3
    x = np.array([560.0e3, 560.0e3 + dx])
    for y_value, expected in [(40.0e3, 0.0), (0.0, 2.0e-5), (80.0e3, 2.0e-5)]:
        lat, lon = get_lat_lon(x, np.array([y_value] * 2))
        distance = _great_circle_distance(lat[0], lon[0], lat[1], lon[1])
        # planar lengths along x exceed the sphere's away from the centerline
        assert dx / distance - 1.0 == pytest.approx(expected, abs=1e-6)


def test_add_lat_lon():
    ds_mesh = make_planar_hex_mesh(
        nx=4, ny=4, dc=1.0e3, nonperiodic_x=True, nonperiodic_y=True
    )
    add_lat_lon(ds_mesh)
    for loc, dim in [
        ('Cell', 'nCells'),
        ('Edge', 'nEdges'),
        ('Vertex', 'nVertices'),
    ]:
        lat, lon = get_lat_lon(ds_mesh[f'x{loc}'], ds_mesh[f'y{loc}'])
        assert ds_mesh[f'lat{loc}'].dims == (dim,)
        np.testing.assert_allclose(ds_mesh[f'lat{loc}'].values, lat)
        np.testing.assert_allclose(ds_mesh[f'lon{loc}'].values, lon)


def _hexagon(radius):
    """A hexagon with vertical sides, centered on the origin"""
    angles = np.deg2rad(np.arange(30.0, 360.0, 60.0))
    return radius * np.cos(angles), radius * np.sin(angles)


def test_clip_hexagon_on_a_wall():
    x, y = _hexagon(1.0)
    area = _polygon_area(x, y)

    x_clipped, y_clipped = clip_polygon_to_y_band(x, y, y_min=0.0)
    assert len(x_clipped) == 5
    assert np.all(y_clipped >= 0.0)
    assert _polygon_area(x_clipped, y_clipped) == pytest.approx(0.5 * area)

    x_clipped, y_clipped = clip_polygon_to_y_band(x, y, y_max=0.0)
    assert np.all(y_clipped <= 0.0)
    assert _polygon_area(x_clipped, y_clipped) == pytest.approx(0.5 * area)


def test_clip_leaves_an_interior_polygon_alone():
    x, y = _hexagon(1.0)
    x_clipped, y_clipped = clip_polygon_to_y_band(x, y, y_min=-2.0, y_max=2.0)
    np.testing.assert_allclose(x_clipped, x)
    np.testing.assert_allclose(y_clipped, y)


def test_write_scrip(tmp_path):
    # culling removes the periodic connections along the boundaries
    ds_mesh = cull(
        make_planar_hex_mesh(
            nx=6, ny=6, dc=1.0e3, nonperiodic_x=True, nonperiodic_y=True
        )
    )
    # put the first row of cells on a wall at y = 0
    y_wall = ds_mesh.yCell.values.min()
    for loc in ['Cell', 'Edge', 'Vertex']:
        ds_mesh[f'y{loc}'] = ds_mesh[f'y{loc}'] - y_wall

    filename = str(tmp_path / 'scrip.nc')
    write_scrip(ds_mesh, filename, y_min=0.0)
    ds = xr.open_dataset(filename)

    ncells = ds_mesh.sizes['nCells']
    assert ds.sizes['grid_size'] == ncells
    assert ds.grid_dims.values.tolist() == [ncells]
    assert np.all(ds.grid_imask.values == 1)
    np.testing.assert_allclose(
        ds.grid_area.values, ds_mesh.areaCell.values / SPHERE_RADIUS**2
    )
    for var in ['grid_center_lon', 'grid_corner_lon']:
        assert np.all(ds[var].values >= 0.0)
        assert np.all(ds[var].values < 2.0 * np.pi)

    # every corner is on or north of the wall, and the wall cells are halved
    corner_x, corner_y = _to_planar(
        ds.grid_corner_lat.values, ds.grid_corner_lon.values
    )
    assert np.all(corner_y >= -1e-3)
    on_wall = np.isclose(ds_mesh.yCell.values, 0.0, atol=1.0)
    assert np.any(on_wall)
    for i_cell in range(ncells):
        area = _polygon_area(corner_x[i_cell, :], corner_y[i_cell, :])
        expected = ds_mesh.areaCell.values[i_cell]
        if on_wall[i_cell]:
            expected = 0.5 * expected
        assert area == pytest.approx(expected, rel=1e-6)


def test_grid_names():
    config = PolarisConfigParser()
    config.add_from_package('polaris.tasks.e3sm.init.misomip', 'misomip.cfg')
    with pytest.raises(ValueError):
        get_grid_names(config)

    config.add_from_package(
        'polaris.tasks.e3sm.init.misomip', 'misomip-o4km-li1km.cfg'
    )
    assert get_grid_names(config) == {
        'ocean': 'misomip-o4km',
        'landice': 'misomip-li1km',
        'model': 'misomip-o4km-li1km',
    }


def test_every_pair_names_its_grids():
    for mesh_name in MESH_PAIRS:
        _, config = get_misomip_mesh_steps(mesh_name)
        grids = get_grid_names(config)
        assert grids['model'] == mesh_name
        assert grids['landice'] == 'misomip-li1km'


def test_mesh_steps_are_shared():
    steps, config = get_misomip_mesh_steps('misomip-o4km-li1km')
    steps_again, config_again = get_misomip_mesh_steps('misomip-o4km-li1km')
    assert config_again is config
    for name, step in steps.items():
        assert steps_again[name] is step
    assert steps['ocean_mesh'].path == (
        'e3sm/init/misomip-o4km-li1km/ocean_mesh'
    )
    assert steps['isomip_plus/topo/cull_mesh'].path == (
        'ocean/planar/isomip_plus/4km/topo/cull_mesh'
    )
    assert steps['mismip_plus/mesh'].path == 'mesh/planar/mismip_plus/1km/mesh'
    for map_name in ['landice_to_ocean_aave', 'ocean_to_landice_aave']:
        assert f'maps/{map_name}' in steps
    assert steps['ocean_partitions'].basename == 'mpas-o.graph.info'
    assert steps['landice_partitions'].basename == 'mpasli.graph.info'
    assert steps['landice_partitions'].section == 'misomip_landice_partitions'


def test_partitions_include_the_planned_task_counts():
    _, config = get_misomip_mesh_steps('misomip-o4km-li1km')
    section = config['misomip_ocean_partitions']
    bounds = dict(
        max_cells_per_core=section.getint('max_cells_per_core'),
        min_cells_per_core=section.getint('min_cells_per_core'),
    )
    # the 4 km ocean mesh has 2759 cells, and the 2 km one about 4 times as
    # many
    cores_4km = get_core_list(ncells=2759, **bounds)
    cores_2km = get_core_list(ncells=4 * 2759, **bounds)
    assert 8 in cores_4km
    assert 36 in cores_2km
    assert 256 in cores_2km


def test_unknown_mesh_pair():
    with pytest.raises(ValueError):
        get_misomip_mesh_steps('misomip-o8km-li1km')
