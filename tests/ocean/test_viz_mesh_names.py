"""
Unit tests for plotting on a mesh written with Omega's names.

The shared plotting helper no longer maps Omega names back to MPAS-Ocean
names itself.  The ocean viz steps open the mesh with
``open_model_dataset()``, which does, and pass the dataset in.
"""

from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.viz.spherical import plot_global_mpas_field
from tests.viz.test_cull_mesh_to_cells import _quad_mesh_dataset


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_a_mesh_opened_by_the_ocean_reader_can_be_plotted(tmp_path, model):
    component = Ocean()
    component.model = model
    component._read_var_map()
    mesh_filename = str(tmp_path / 'mesh.nc')
    _write_mesh(component, mesh_filename)
    reader_config = ConfigParser()
    reader_config.add_section('ocean')
    reader_config.set('ocean', 'model', model)
    out_filename = tmp_path / 'field.png'

    mesh_ds = component.open_model_dataset(mesh_filename, reader_config)
    plot_global_mpas_field(
        mesh_ds=mesh_ds,
        da=xr.DataArray(np.linspace(0.0, 1.0, 16), dims=('nCells',)),
        out_filename=str(out_filename),
        config=_colormap_config(),
        colormap_section='test_viz',
        plot_land=False,
    )

    assert out_filename.exists()


def test_an_omega_mesh_file_has_names_the_plot_cannot_use(tmp_path):
    """Why the ocean viz steps have to open the mesh themselves."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    mesh_filename = str(tmp_path / 'mesh.nc')
    _write_mesh(component, mesh_filename)

    ds = xr.open_dataset(mesh_filename)

    assert 'NCells' in ds.dims
    assert 'VerticesOnCell' in ds
    assert 'verticesOnCell' not in ds


def _write_mesh(component, filename):
    """Write a small mesh in the names ``component.model`` uses."""
    mesh_ds = _quad_mesh_dataset(4, 4)
    if component.model == 'omega':
        rename = {
            k: v
            for k, v in component.mpaso_to_omega_dim_map.items()
            if k in mesh_ds.dims
        }
        rename.update(
            {
                k: v
                for k, v in component.mpaso_to_omega_var_map.items()
                if k in mesh_ds
            }
        )
        mesh_ds = mesh_ds.rename(rename)
    mesh_ds.to_netcdf(filename)


def _colormap_config():
    config = PolarisConfigParser()
    config.set('test_viz', 'colormap_name', 'viridis')
    config.set('test_viz', 'norm_type', 'linear')
    config.set('test_viz', 'norm_args', "{'vmin': 0.0, 'vmax': 1.0}")
    return config
