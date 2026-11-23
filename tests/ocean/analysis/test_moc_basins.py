"""
Unit tests for the overturning of each basin, which the moc step computes
offline from the shared climatology.

The kernel is tested in ``tests/ocean/test_overturning.py``; what is tested
here is the step around it: that the basins are found by name in the mask
file, that the fields are read under Omega's names from the annual
climatology, that the streamfunction comes out where the transport says it
should, and that a climatology without the transport velocity is reported
rather than failing.  The mesh is a 10-degree latitude-longitude grid with
two layers, written with Omega's names and dimensions.
"""

import json
import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis.analysis_step import (
    MESH_FILENAME,
    VERT_COORD_FILENAME,
)
from polaris.tasks.ocean.analysis.climatology import Climatology
from polaris.tasks.ocean.analysis.moc import MASKS_FILENAME
from polaris.tasks.ocean.analysis.moc_basins import (
    get_moc_elevations,
    get_moc_latitudes,
)
from polaris.tasks.ocean.analysis.sim_files import SimulationFiles
from tests.ocean.analysis.test_moc_step import make_step as make_moc_step
from tests.ocean.analysis.test_sim_files import omega_month_time
from tests.ocean.latlon_mesh import EARTH_RADIUS, latlon_mesh

# the speed of the upper layer, northward, over a lower layer flowing south
# as fast, in the annual climatology
SPEED = 0.1

# two layers of uniform thickness
THICKNESS = 100.0
N_LEVELS = 2

# the basins of the synthetic mask file: the western and eastern halves of
# the sphere, under the names of real MOC basins
WEST = 'Atlantic'
EAST = 'IndoPacific'

# what ncclimo names the annual climatology, which the step finds by season
CLIMATOLOGY_FILENAME = 'test_run_ANN_000101_000112_climo.nc'

# what Omega appends to each field of a monthly mean
SUFFIX = '_TimeMean1Month'

# the noleap calendar the simulation is run on
DAYS_IN_MONTH = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])

OMEGA_CONFIG = """\
Omega:
  Analysis:
    MonthlyAverages:
      Enable: true
      Filename: monthly_means.$Y-$M.nc
      ReductionPeriod: [1Month]
"""


def test_elevations_follow_the_spacing_to_the_deepest_floor():
    config = _config()
    config.set('ocean_analysis_moc', 'elevation_spacing', '10.0, 50.0')
    config.set('ocean_analysis_moc', 'spacing_break_depths', '30.0')
    z = get_moc_elevations(config, max_depth=120.0)
    np.testing.assert_allclose(z, [0.0, -10.0, -20.0, -30.0, -80.0, -130.0])


def test_a_spacing_that_overshoots_a_break_stops_at_it():
    config = _config()
    config.set('ocean_analysis_moc', 'elevation_spacing', '20.0, 50.0')
    config.set('ocean_analysis_moc', 'spacing_break_depths', '30.0')
    z = get_moc_elevations(config, max_depth=60.0)
    np.testing.assert_allclose(z, [0.0, -20.0, -30.0, -80.0])


@pytest.mark.parametrize(
    'spacing, breaks',
    [('10.0', '200.0'), ('10.0, -5.0', '200.0'), ('1.0, 2.0, 3.0', '9, 4')],
)
def test_inconsistent_elevation_spacing_is_an_error(spacing, breaks):
    config = _config()
    config.set('ocean_analysis_moc', 'elevation_spacing', spacing)
    config.set('ocean_analysis_moc', 'spacing_break_depths', breaks)
    with pytest.raises(ValueError, match='ocean_analysis_moc'):
        get_moc_elevations(config, max_depth=100.0)


def test_latitudes_span_the_poles():
    config = _config()
    config.set('ocean_analysis_moc', 'dlat', '45.0')
    np.testing.assert_allclose(
        get_moc_latitudes(config), [-90.0, -45.0, 0.0, 45.0, 90.0]
    )


def test_each_basin_carries_its_share_of_the_overturning(tmp_path):
    """Each half of the sphere carries half of a zonally uniform
    overturning, positive with northward flow above southward"""
    step = _make_step(tmp_path)
    step.run()
    half_length = np.pi * EARTH_RADIUS
    # the transport below each elevation, from the top down: the upper layer
    # flows north, the lower one south
    expected = SPEED * half_length * np.array([0, 50, 100, 50, 0]) / 1e6
    for name in ['atlantic', 'indo_pacific']:
        ds = _read_basin(step, f'{name}_ANN')
        np.testing.assert_allclose(ds.z.values, [0, -50, -100, -150, -200])
        equator = int(np.argmin(np.abs(ds.lat.values)))
        np.testing.assert_allclose(
            ds.mocStreamfunction.isel(nLatitudes=equator).values,
            expected,
            rtol=1e-10,
            atol=1e-10,
        )
        assert ds.attrs['season'] == 'ANN'


@pytest.mark.parametrize(
    'season, months', [('ANN', range(1, 13)), ('DJF', [12, 1, 2])]
)
def test_the_basins_read_what_the_climatology_step_writes(
    tmp_path, season, months
):
    """The climatology step computes each season's climatology of the
    transport velocity from monthly means that speed up month by month, and
    each season's basins come out as that season's day-weighted mean speed
    says"""
    step = _make_step(tmp_path, through_ncclimo=True, plot_seasons='ANN, DJF')
    step.run()
    months = np.asarray(months)
    days = DAYS_IN_MONTH[months - 1]
    mean_month = np.sum(days * months) / days.sum()
    expected = SPEED * mean_month * np.pi * EARTH_RADIUS * 100.0 / 1e6
    ds = _read_basin(step, f'atlantic_{season}')
    assert ds.attrs['season'] == season
    assert np.nanmax(ds.mocStreamfunction.values) == pytest.approx(
        expected, rel=1e-6
    )


def test_a_basin_is_plotted_over_its_configured_latitudes(tmp_path):
    step = _make_step(tmp_path)
    step.config.set('ocean_analysis_moc_atlantic', 'min_lat', '-30.0')
    step.config.set('ocean_analysis_moc_atlantic', 'max_lat', '30.0')
    step.run()
    ds = _read_basin(step, 'atlantic_ANN')
    assert ds.lat.values.min() == pytest.approx(-30.0)
    assert ds.lat.values.max() == pytest.approx(30.0)
    assert ds.attrs['region'] == WEST


def test_a_line_with_no_ocean_is_left_out(tmp_path):
    """A basin without a section is plotted over the lines it has ocean on,
    and the line at the pole has none"""
    step = _make_step(tmp_path)
    step.config.remove_section('ocean_analysis_moc_atlantic')
    step.run()
    ds = _read_basin(step, 'atlantic_ANN')
    assert ds.lat.values.max() < 90.0
    assert np.all(np.isfinite(ds.mocStreamfunction.values))


def test_basins_are_found_by_name_whatever_the_region_dimension(tmp_path):
    """The mask file's basins are in another order, along a dimension of
    another name, and the step still picks each one by its name"""
    step = _make_step(tmp_path, region_dim='nBasins', reverse_masks=True)
    step.run()
    assert _read_basin(step, 'atlantic_ANN').attrs['region'] == WEST
    assert _read_basin(step, 'indo_pacific_ANN').attrs['region'] == EAST


def test_an_unknown_basin_is_an_error_naming_the_known_ones(tmp_path):
    step = _make_step(tmp_path, regions='Atlantic, Arctic')
    with pytest.raises(ValueError, match='Arctic.*Atlantic, IndoPacific'):
        step.run()


def test_each_basin_is_a_gallery_of_the_moc_group(tmp_path):
    """Each basin is one gallery of the moc group, with a plot for each
    season, as each field of the maps is"""
    step = _make_step(tmp_path, through_ncclimo=True, plot_seasons='ANN, JJA')
    step.run()
    products = _products(step)
    assert sorted(
        (product['gallery'], product['season']) for product in products
    ) == [
        ('atlantic', 'ANN'),
        ('atlantic', 'JJA'),
        ('indo_pacific', 'ANN'),
        ('indo_pacific', 'JJA'),
    ]
    for product in products:
        assert product['group'] == 'moc'
        assert os.path.exists(step.work_path(product['plot']))
        assert os.path.exists(step.work_path(product['data']))


def test_a_climatology_without_the_transport_velocity_is_reported(
    tmp_path, caplog
):
    """Simulations that predate writing the transport velocity are met; the
    step says what to add and makes no basin plots"""
    step = _make_step(tmp_path, with_velocity=False)
    with caplog.at_level(logging.INFO):
        step.run()
    assert 'NormalTransportVelocity' in caplog.text
    assert 'MonthlyAverages' in caplog.text
    assert _products(step) == []


def _config():
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    return config


def _read_basin(step, name):
    with xr.open_dataset(step.work_path(f'{name}.nc')) as ds:
        return ds.load()


def _products(step):
    with open(step.work_path('manifest.json')) as manifest:
        return json.load(manifest)['products']


def _write_inputs(path, ds_mesh, with_velocity, region_dim, reverse, config):
    """The mesh, vertical coordinate, basin masks and annual climatology,
    with Omega's names as the climatology step leaves them, or computed by
    that step if a config is given"""
    xr.Dataset(
        dict(
            CellsOnEdge=(
                ('NEdges', 'MaxCellsOnEdge'),
                ds_mesh.cellsOnEdge.values,
            ),
            LatCell=('NCells', ds_mesh.latCell.values),
            LonCell=('NCells', ds_mesh.lonCell.values),
            DvEdge=('NEdges', ds_mesh.dvEdge.values),
            DcEdge=('NEdges', ds_mesh.dcEdge.values),
        )
    ).to_netcdf(os.path.join(path, 'mesh.nc'))

    n_cells = ds_mesh.sizes['nCells']
    xr.Dataset(
        dict(
            MinLayerCell=('NCells', np.ones(n_cells, dtype=np.int32)),
            MaxLayerCell=('NCells', np.full(n_cells, N_LEVELS, np.int32)),
            BottomGeomDepth=('NCells', np.full(n_cells, N_LEVELS * THICKNESS)),
        )
    ).to_netcdf(os.path.join(path, 'vert_coord.nc'))

    lat1, lat2 = (
        ds_mesh.latCell.values[ds_mesh.cellsOnEdge.values[:, i] - 1]
        for i in range(2)
    )
    northward = np.sign(lat2 - lat1)
    profile = northward[:, np.newaxis] * np.array([SPEED, -SPEED])
    z_interface = -THICKNESS * np.arange(N_LEVELS + 1)
    data = {
        'PseudoThickness': (
            ('time', 'NCells', 'NVertLayers'),
            np.full((1, n_cells, N_LEVELS), THICKNESS),
        ),
        'GeomZInterface': (
            ('time', 'NCells', 'NVertLayersP1'),
            np.tile(z_interface, (1, n_cells, 1)),
        ),
    }
    if with_velocity:
        data['NormalTransportVelocity'] = (
            ('time', 'NEdges', 'NVertLayers'),
            profile[np.newaxis, :, :],
        )
    climatology_dir = os.path.join(path, 'climatology')
    os.makedirs(climatology_dir)
    if config is None:
        xr.Dataset(data).to_netcdf(
            os.path.join(climatology_dir, CLIMATOLOGY_FILENAME)
        )
    else:
        _run_climatology(climatology_dir, data, config)

    west = np.rad2deg(ds_mesh.lonCell.values) < 180.0
    masks = np.stack([west, ~west], axis=1).astype(np.int32)
    names = [f'{WEST}_MOC', f'{EAST}_MOC']
    if reverse:
        masks = masks[:, ::-1]
        names = names[::-1]
    xr.Dataset(
        dict(
            regionCellMasks=(('NCells', region_dim), masks),
            regionNames=((region_dim,), names),
        )
    ).to_netcdf(os.path.join(path, 'masks.nc'))
    return climatology_dir


def _run_climatology(climatology_dir, data, config):
    """Write the months of a year, each faster than the last, and run the
    climatology step on them"""
    with open(os.path.join(climatology_dir, 'omega.yml'), 'w') as handle:
        handle.write(OMEGA_CONFIG)
    config.set(
        'ocean_analysis',
        'omega_config_filename',
        os.path.join(climatology_dir, 'omega.yml'),
    )
    for month in range(1, 13):
        ds = xr.Dataset(
            {
                f'{name}{SUFFIX}': (
                    dims,
                    month * values if name.endswith('Velocity') else values,
                )
                for name, (dims, values) in data.items()
            }
        )
        named_year, named_month = (2, 1) if month == 12 else (1, month + 1)
        filename = (
            f'monthly_means_1MonthTimeStats.'
            f'{named_year:04d}-{named_month:02d}.nc'
        )
        ds = xr.merge([ds, omega_month_time(1, month)])
        ds.to_netcdf(
            os.path.join(climatology_dir, filename), unlimited_dims=['time']
        )

    sim_files = SimulationFiles(config, log=lambda message: None)
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    step = Climatology(
        component=component,
        subdir='analysis/climatology/0001-0001',
        start_year=1,
        end_year=1,
    )
    step.work_dir = climatology_dir
    step.config = config
    step.logger = logging.getLogger('climatology')
    step.input_filenames = [
        os.path.basename(sim_file.path)
        for sim_file in sim_files.monthly_mean_files(1, 1)
    ]
    step.run()


def _make_step(
    tmp_path,
    with_velocity=True,
    region_dim='nRegions',
    reverse_masks=False,
    regions=None,
    through_ncclimo=False,
    plot_seasons='ANN',
):
    """A moc step with no global output, given the inputs of the basins as
    setup() and the climatology step would"""
    work_dir = tmp_path / 'moc'
    work_dir.mkdir()
    step = make_moc_step(work_dir)
    step.has_moc_output = False
    step.has_basins = True
    config = step.config
    config.set('ocean_analysis_moc', 'regions', regions or f'{WEST}, {EAST}')
    config.set('ocean_analysis_moc', 'elevation_spacing', '50.0')
    config.set('ocean_analysis_moc', 'spacing_break_depths', '')
    # only the annual climatology is written unless ncclimo computes them
    config.set('ocean_analysis_climatology', 'plot_seasons', plot_seasons)
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    climatology_dir = _write_inputs(
        str(inputs),
        latlon_mesh(),
        with_velocity,
        region_dim,
        reverse_masks,
        config if through_ncclimo else None,
    )
    step.dependencies['climatology'].work_dir = climatology_dir
    for source, link in [
        ('mesh.nc', MESH_FILENAME),
        ('vert_coord.nc', VERT_COORD_FILENAME),
        ('masks.nc', MASKS_FILENAME),
    ]:
        os.symlink(inputs / source, work_dir / link)
    step.runtime_setup()
    return step
