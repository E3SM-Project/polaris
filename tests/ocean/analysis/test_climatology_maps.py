"""
Unit tests for the climatology map step.

What is checked here is the bookkeeping around the plots rather than the
plots themselves: that every PNG has a netCDF beside it, that a field the
simulation did not write is skipped rather than failing the step, and that
the vertical geometry, which nothing can stand in for, stops it instead.
Plotting is stubbed out, since drawing a global mesh needs a mesh.

The two reductions that read that geometry are checked on their values as
well, since the synthetic grid is uniform and shallow enough for both to be
written down: an elevation halfway between two layer midpoints, and a heat
content range ending halfway through a layer.

Heat content is the one field group that derives its field instead of
reading it, so what it adds is that the value written is the one the kernel
gives, in the unit the file claims, while what is plotted is in another.

Velocity components the simulation did not write are reconstructed from the
edge-normal velocity.  The reconstruction itself is tested with the mesh
operators, so the mesh here carries weights simple enough to write the answer
down: each cell reads one edge, and every cell sits at the origin of latitude
and longitude, where the zonal and meridional directions are y and z.
"""

import json
import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import (
    climatology_maps as climatology_maps_module,
)
from polaris.tasks.ocean.analysis.climatology import Climatology
from polaris.tasks.ocean.analysis.climatology_maps import (
    ClimatologyMaps,
    get_field_groups,
)

N_CELLS = 5
N_LEVELS = 4

# a uniform layer thickness, so that the heat content of a column is a number
# that can be written down
THICKNESS = 100.0

# the geometry that thickness implies, the same in every column
Z_INTERFACE = -THICKNESS * np.arange(N_LEVELS + 1)[None, None, :]
Z_MID = 0.5 * (Z_INTERFACE[:, :, :-1] + Z_INTERFACE[:, :, 1:])

SEASONS = ['ANN', 'JJA']

VELOCITY_FIELDS = ['velocityZonal', 'velocityMeridional']

# one edge per cell, so that each cell's stencil is the edge of the same index
N_EDGES = N_CELLS

# the edge that is closed in the bottom layer
CLOSED_EDGE = 2


def test_a_netcdf_is_registered_beside_every_plot(step):
    step.run()
    outputs = [os.path.basename(output) for output in step.outputs]
    images = [name for name in outputs if name.endswith('.png')]
    assert images
    for image in images:
        assert image.replace('.png', '.nc') in outputs


def test_each_map_is_described_in_the_manifest(step):
    step.runtime_setup()
    step.run()
    with open(os.path.join(step.work_dir, 'manifest.json')) as manifest:
        products = json.load(manifest)['products']

    # every plot the step made is described, and nothing else is
    assert {product['plot'] for product in products} == _images(step)

    for product in products:
        assert product['group'] == 'climatology_maps'
        assert product['gallery'] == 'temperature'
        assert product['field'] == 'temperature'
        assert product['season'] in SEASONS
        assert product['data'] == product['plot'].replace('.png', '.nc')
        assert product['reduction'] in product['plot']

    # order is meaning: the seasons appear in the order they were plotted,
    # which is what lets the gallery read ANN, DJF, MAM, JJA, SON with no
    # sort key anywhere
    seasons = list(dict.fromkeys(product['season'] for product in products))
    assert seasons == SEASONS


def test_a_map_is_plotted_for_each_season_and_reduction(step):
    step.run()
    images = _images(step)
    assert images == {
        f'temperature_{season}_{label}.png'
        for season in SEASONS
        for label in ('top', 'bottom', 'k1')
    }


def test_the_registered_outputs_are_the_files_that_were_written(step):
    step.run()
    for output in step.outputs:
        assert os.path.exists(output), output


def test_a_field_with_no_vertical_dimension_has_no_reduction_label(ssh_step):
    ssh_step.run()
    assert _images(ssh_step) == {f'ssh_{season}.png' for season in SEASONS}


def test_a_field_the_simulation_did_not_write_is_skipped(step, caplog):
    """The climatology has temperature but not salinity."""
    step.fields = ['temperature', 'salinity']
    with caplog.at_level(logging.INFO):
        step.run()
    assert 'did not write salinity' in caplog.text
    assert not any(name.startswith('salinity') for name in _images(step))
    assert any(name.startswith('temperature') for name in _images(step))


def test_a_map_is_plotted_at_an_elevation(step):
    step.config.set(
        'ocean_analysis_climatology',
        'elevations',
        'top, -100.0, bottom',
        user=True,
    )
    step.run()
    assert _images(step) == {
        f'temperature_{season}_{label}.png'
        for season in SEASONS
        for label in ('top', '-100m', 'bottom')
    }


def test_the_map_at_an_elevation_is_the_interpolated_field(step):
    """-100 m is midway between the midpoints of the top two layers of this
    uniform 100 m grid, so the value there is the average of the two."""
    step.config.set(
        'ocean_analysis_climatology', 'elevations', '-100.0', user=True
    )
    step.run()
    with xr.open_dataset(
        os.path.join(step.work_dir, 'temperature_ANN_-100m.nc')
    ) as ds:
        values = ds.temperature.values
    for cell in range(N_CELLS):
        # the climatology holds cell + 10 * level for season ANN
        assert values[cell] == pytest.approx(cell + 5.0)


def test_a_map_at_an_elevation_needs_the_geometry_the_model_wrote(
    step, tmp_path
):
    """A simulation that did not write it is out of spec rather than merely
    configured without a field, and there is nothing to reconstruct it
    from, so this stops the step instead of skipping a plot."""
    for filename in os.listdir(str(tmp_path / 'climatology')):
        path = str(tmp_path / 'climatology' / filename)
        with xr.open_dataset(path) as ds:
            trimmed = ds.drop_vars(['GeomZMid', 'GeomZInterface']).load()
        trimmed.to_netcdf(path)
    with pytest.raises(ValueError, match='no zMid, GeomZInterface'):
        step.run()


def test_velocity_components_are_reconstructed_from_normal_velocity(
    velocity_step, caplog
):
    with caplog.at_level(logging.INFO):
        velocity_step.run()
    assert 'reconstructing velocityZonal, velocityMeridional' in caplog.text
    assert _images(velocity_step) == {
        f'{field}_{season}_{label}.png'
        for field in VELOCITY_FIELDS
        for season in SEASONS
        for label in ('top', 'bottom', 'k1')
    }
    # the climatology holds edge + 10 * level for season ANN, and cell i
    # reads edge i with weights that give it that value in y and twice that
    # in z
    expected = np.arange(N_CELLS) + 10.0
    zonal = _read_map(velocity_step, 'velocityZonal_ANN_k1.nc')
    meridional = _read_map(velocity_step, 'velocityMeridional_ANN_k1.nc')
    np.testing.assert_allclose(zonal.values, expected)
    np.testing.assert_allclose(meridional.values, 2.0 * expected)
    assert zonal.attrs['units'] == 'm s-1'
    assert 'reconstructed' in zonal.attrs['long_name']


def test_a_closed_edge_carries_no_flow(velocity_step):
    """An edge below the seafloor is fill in the monthly means; nothing
    crosses it, so it contributes zero rather than poisoning the cell."""
    velocity_step.run()
    zonal = _read_map(velocity_step, 'velocityZonal_ANN_bottom.nc')
    assert zonal.values[CLOSED_EDGE] == 0.0
    assert np.all(np.isfinite(zonal.values))


def test_components_the_simulation_wrote_are_not_reconstructed(
    velocity_step, tmp_path, caplog
):
    """Reconstruction is a fallback for a model that does not write the
    components, so what the model wrote is what is plotted."""
    for filename in os.listdir(str(tmp_path / 'climatology')):
        path = str(tmp_path / 'climatology' / filename)
        with xr.open_dataset(path) as ds:
            ds = ds.load()
        written = xr.full_like(ds.Temperature, -1.0)
        ds['velocityZonal'] = written
        ds['velocityMeridional'] = written
        ds.to_netcdf(path)
    with caplog.at_level(logging.INFO):
        velocity_step.run()
    assert 'reconstructing' not in caplog.text
    zonal = _read_map(velocity_step, 'velocityZonal_ANN_k1.nc')
    np.testing.assert_allclose(zonal.values, -1.0)


def test_reconstruction_needs_the_weights_in_the_mesh(velocity_step):
    _write_mesh_and_vert_coord(velocity_step.work_dir)
    with pytest.raises(ValueError, match='cannot be reconstructed'):
        velocity_step.run()


def test_the_field_groups_cover_the_fields_that_are_asked_for():
    groups = get_field_groups(['ssh', 'temperature'])
    assert groups['temperature'] == ['temperature']
    assert groups['ssh'] == ['ssh']
    # heat content is derived, so it is always there
    assert groups['heat_content'] == []


def test_a_field_in_no_group_is_reported():
    with pytest.raises(ValueError, match='belongs to no field group'):
        get_field_groups(['notAField'])


@pytest.fixture
def step(tmp_path, monkeypatch):
    return _make_step(tmp_path, monkeypatch, 'temperature', ['temperature'])


@pytest.fixture
def ssh_step(tmp_path, monkeypatch):
    return _make_step(tmp_path, monkeypatch, 'ssh', ['ssh'])


@pytest.fixture
def velocity_step(tmp_path, monkeypatch):
    step = _make_step(tmp_path, monkeypatch, 'velocity', VELOCITY_FIELDS)
    _write_reconstruction_mesh(step.work_dir)
    return step


def _make_step(tmp_path, monkeypatch, field_group, fields):
    """A map step with a synthetic climatology to read and plotting stubbed"""
    monkeypatch.setattr(
        climatology_maps_module, 'plot_global_mpas_field', _fake_plot
    )

    work_dir = tmp_path / field_group
    climatology_dir = tmp_path / 'climatology'
    work_dir.mkdir(parents=True)
    climatology_dir.mkdir(parents=True)
    _write_climatology(str(climatology_dir))
    _write_mesh_and_vert_coord(str(work_dir))

    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean', 'model', 'omega')
    config.set(
        'ocean_analysis_climatology',
        'plot_seasons',
        ', '.join(SEASONS),
        user=True,
    )
    config.set(
        'ocean_analysis_climatology',
        'elevations',
        'top, bottom, k1',
        user=True,
    )

    component = Ocean()
    component.model = 'omega'

    climatology = Climatology(
        component=component,
        subdir='analysis/climatology/0001-0003',
        start_year=1,
        end_year=3,
    )
    climatology.work_dir = str(climatology_dir)
    step = ClimatologyMaps(
        component=component,
        subdir=f'analysis/climatology_maps/0001-0003/{field_group}',
        field_group=field_group,
        fields=fields,
        start_year=1,
        end_year=3,
        climatology=climatology,
    )
    step.work_dir = str(work_dir)
    step.config = config
    step.logger = logging.getLogger('climatology_maps')
    step.input_filenames = ['mesh.nc', 'vert_coord.nc']
    step.outputs = []
    step.dependencies['climatology'] = climatology
    return step


def _fake_plot(da, out_filename, config, colormap_section, **kwargs):
    """Write a placeholder in place of the plot, and hand back a descriptor
    so that the step's reuse of one can be seen to work."""
    assert colormap_section.startswith('ocean_analysis_map_')
    # the helper reads MPAS-Ocean names, not the Omega names of the file
    assert 'nCells' in kwargs['mesh_ds'].dims
    with open(out_filename, 'w') as image:
        image.write('not really a plot\n')
    return kwargs.get('descriptor') or 'descriptor'


def _write_climatology(climatology_dir):
    """One ncclimo-style file per season, with Omega names"""
    cells = np.arange(N_CELLS)[:, None]
    levels = np.arange(N_LEVELS)[None, :]
    edges = np.arange(N_EDGES)[:, None]
    for index, season in enumerate(SEASONS):
        normal_velocity = (index + edges + 10.0 * levels)[None, :, :]
        normal_velocity[0, CLOSED_EDGE, -1] = np.nan
        ds = xr.Dataset(
            dict(
                Temperature=(
                    ('time', 'NCells', 'NVertLayers'),
                    (index + cells + 10.0 * levels)[None, :, :],
                ),
                SshCell=(('time', 'NCells'), (index + cells.T)),
                NormalVelocity=(
                    ('time', 'NEdges', 'NVertLayers'),
                    normal_velocity,
                    {'units': 'm s-1'},
                ),
                PseudoThickness=(
                    ('time', 'NCells', 'NVertLayers'),
                    np.full((1, N_CELLS, N_LEVELS), THICKNESS),
                ),
                GeomZInterface=(
                    ('time', 'NCells', 'NVertLayersP1'),
                    np.tile(Z_INTERFACE, (1, N_CELLS, 1)),
                ),
                GeomZMid=(
                    ('time', 'NCells', 'NVertLayers'),
                    np.tile(Z_MID, (1, N_CELLS, 1)),
                ),
            )
        )
        ds.to_netcdf(f'{climatology_dir}/case_{season}_000101_000312_climo.nc')


def _write_mesh_and_vert_coord(work_dir):
    """The mesh and vertical coordinate the step reads, with Omega names"""
    ds_mesh = xr.Dataset(
        dict(
            LatCell=('NCells', np.linspace(-1.0, 1.0, N_CELLS)),
            LonCell=('NCells', np.linspace(0.0, 6.0, N_CELLS)),
        )
    )
    ds_mesh.to_netcdf(f'{work_dir}/mesh.nc')
    ds_vert = xr.Dataset(
        dict(
            MinLayerCell=('NCells', np.ones(N_CELLS, dtype=int)),
            MaxLayerCell=(
                'NCells',
                np.full(N_CELLS, N_LEVELS, dtype=int),
            ),
        )
    )
    ds_vert.to_netcdf(f'{work_dir}/vert_coord.nc')


def _write_reconstruction_mesh(work_dir):
    """A mesh whose weights are simple enough to write the answer down"""
    stencil = np.zeros((N_CELLS, 2), dtype=int)
    stencil[:, 0] = np.arange(N_CELLS) + 1
    weights = np.zeros((N_CELLS, 3, 2))
    # y and z, which are zonal and meridional at the origin
    weights[:, 1, 0] = 1.0
    weights[:, 2, 0] = 2.0
    ds_mesh = xr.Dataset(
        dict(
            LatCell=('NCells', np.zeros(N_CELLS)),
            LonCell=('NCells', np.zeros(N_CELLS)),
            ReconStencilCell=(('NCells', 'MaxEdges2'), stencil),
            ReconWeightsCell=(('NCells', 'R3', 'MaxEdges2'), weights),
        )
    )
    ds_mesh.to_netcdf(f'{work_dir}/mesh.nc')


def _read_map(step, filename):
    """Read the field written beside one plot"""
    with xr.open_dataset(os.path.join(step.work_dir, filename)) as ds:
        return ds[ds.attrs['field']].load()


def _images(step):
    """The base names of the images the step wrote"""
    return {
        name for name in os.listdir(step.work_dir) if name.endswith('.png')
    }
