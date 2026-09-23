"""
Unit tests for the mesh a spherical plot is drawn on.

``plot_global_mpas_field()`` is framework code, so it must not ask which
component called it.  It used to read ``[ocean] model`` to decide whether to
map Omega names back to MPAS-Ocean names, which raised ``NoSectionError`` in
every other component.  Now the caller hands it a mesh with MPAS names.
"""

import mosaic
import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.viz.spherical import plot_global_mpas_field
from tests.viz.test_cull_mesh_to_cells import _quad_mesh_dataset


def test_a_mesh_file_plots_without_an_ocean_section(tmp_path):
    """The case that broke the mesh and e3sm/init viz steps."""
    mesh_filename = str(tmp_path / 'mesh.nc')
    mesh_ds = _quad_mesh_dataset(4, 4)
    mesh_ds.to_netcdf(mesh_filename)
    config = _colormap_config()
    config.set('mesh', 'model', 'mpas-ocean')
    assert not config.has_section('ocean')
    out_filename = tmp_path / 'field.png'

    plot_global_mpas_field(
        mesh_filename=mesh_filename,
        da=_cell_field(mesh_ds),
        out_filename=str(out_filename),
        config=config,
        colormap_section='test_viz',
        plot_land=False,
    )

    assert out_filename.exists()


def test_a_mesh_dataset_plots_in_place_of_a_file(tmp_path):
    mesh_ds = _quad_mesh_dataset(4, 4)
    out_filename = tmp_path / 'field.png'

    plot_global_mpas_field(
        mesh_ds=mesh_ds,
        da=_cell_field(mesh_ds),
        out_filename=str(out_filename),
        config=_colormap_config(),
        colormap_section='test_viz',
        plot_land=False,
    )

    assert out_filename.exists()


def test_the_callers_mesh_dataset_is_left_alone(tmp_path):
    """The caller may go on using the dataset it passed in."""
    mesh_ds = _quad_mesh_dataset(4, 4)
    del mesh_ds.attrs['is_periodic']
    cell_indices = np.array([5, 6, 9, 10])

    plot_global_mpas_field(
        mesh_ds=mesh_ds,
        da=_cell_field(mesh_ds).isel(nCells=cell_indices),
        out_filename=str(tmp_path / 'field.png'),
        config=_colormap_config(),
        colormap_section='test_viz',
        plot_land=False,
        cell_indices=cell_indices,
    )

    assert 'is_periodic' not in mesh_ds.attrs
    assert mesh_ds.sizes['nCells'] == 16


def test_the_descriptor_is_returned_for_reuse(tmp_path):
    mesh_ds = _quad_mesh_dataset(4, 4)
    da = _cell_field(mesh_ds)
    config = _colormap_config()

    descriptor = plot_global_mpas_field(
        mesh_ds=mesh_ds,
        da=da,
        out_filename=str(tmp_path / 'first.png'),
        config=config,
        colormap_section='test_viz',
        plot_land=False,
    )
    assert isinstance(descriptor, mosaic.Descriptor)

    out_filename = tmp_path / 'second.png'
    reused = plot_global_mpas_field(
        da=da,
        out_filename=str(out_filename),
        config=config,
        colormap_section='test_viz',
        plot_land=False,
        descriptor=descriptor,
    )

    assert reused is descriptor
    assert out_filename.exists()


def test_a_culled_descriptor_is_reused_for_culled_fields(tmp_path):
    mesh_ds = _quad_mesh_dataset(4, 4)
    cell_indices = np.array([5, 6, 9, 10])
    da = _cell_field(mesh_ds).isel(nCells=cell_indices)
    config = _colormap_config()

    descriptor = plot_global_mpas_field(
        mesh_ds=mesh_ds,
        da=da,
        out_filename=str(tmp_path / 'first.png'),
        config=config,
        colormap_section='test_viz',
        plot_land=False,
        cell_indices=cell_indices,
    )
    assert descriptor.sizes['nCells'] == len(cell_indices)

    out_filename = tmp_path / 'second.png'
    plot_global_mpas_field(
        da=da,
        out_filename=str(out_filename),
        config=config,
        colormap_section='test_viz',
        plot_land=False,
        descriptor=descriptor,
        cell_indices=cell_indices,
    )

    assert out_filename.exists()


def test_a_mesh_is_required(tmp_path):
    mesh_ds = _quad_mesh_dataset(4, 4)

    with pytest.raises(ValueError, match='mesh_ds'):
        plot_global_mpas_field(
            da=_cell_field(mesh_ds),
            out_filename=str(tmp_path / 'field.png'),
            config=_colormap_config(),
            colormap_section='test_viz',
        )


def _colormap_config():
    """A config with nothing but the colormap a plot needs."""
    config = PolarisConfigParser()
    config.set('test_viz', 'colormap_name', 'viridis')
    config.set('test_viz', 'norm_type', 'linear')
    config.set('test_viz', 'norm_args', "{'vmin': 0.0, 'vmax': 1.0}")
    return config


def _cell_field(mesh_ds):
    n_cells = mesh_ds.sizes['nCells']
    return xr.DataArray(np.linspace(0.0, 1.0, n_cells), dims=('nCells',))
