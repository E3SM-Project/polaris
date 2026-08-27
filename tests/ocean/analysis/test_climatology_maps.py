"""
Unit tests for the climatology map step.

What is checked here is the bookkeeping around the plots rather than the
plots themselves: that every PNG has a netCDF beside it, that a field the
simulation did not write is skipped rather than failing the step, and that a
vertical reduction the machinery cannot reach yet is skipped too.  Plotting
is stubbed out, since drawing a global mesh needs a mesh.
"""

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

SEASONS = ['ANN', 'JJA']


def test_a_netcdf_is_registered_beside_every_plot(step):
    step.run()
    outputs = [os.path.basename(output) for output in step.outputs]
    images = [name for name in outputs if name.endswith('.png')]
    assert images
    for image in images:
        assert image.replace('.png', '.nc') in outputs


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


def test_an_elevation_that_is_not_implemented_yet_is_skipped(step, caplog):
    step.config.set(
        'ocean_analysis_climatology',
        'elevations',
        'top, -100.0, bottom',
        user=True,
    )
    with caplog.at_level(logging.INFO):
        step.run()
    assert 'reducing to -100m' in caplog.text
    assert _images(step) == {
        f'temperature_{season}_{label}.png'
        for season in SEASONS
        for label in ('top', 'bottom')
    }


def test_a_derived_field_group_plots_nothing_yet(step, caplog):
    step.field_group = 'heat_content'
    step.fields = []
    with caplog.at_level(logging.INFO):
        step.run()
    assert 'derived rather than' in caplog.text
    assert not _images(step)


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
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
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
    with open(out_filename, 'w') as image:
        image.write('not really a plot\n')
    return kwargs.get('descriptor') or 'descriptor'


def _write_climatology(climatology_dir):
    """One ncclimo-style file per season, with Omega names"""
    cells = np.arange(N_CELLS)[:, None]
    levels = np.arange(N_LEVELS)[None, :]
    for index, season in enumerate(SEASONS):
        ds = xr.Dataset(
            dict(
                Temperature=(
                    ('time', 'NCells', 'NVertLayers'),
                    (index + cells + 10.0 * levels)[None, :, :],
                ),
                SshCell=(('time', 'NCells'), (index + cells.T)),
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


def _images(step):
    """The base names of the images the step wrote"""
    return {
        name for name in os.listdir(step.work_dir) if name.endswith('.png')
    }
