"""
Shared helpers for the overflow init steps: building the mesh and
computing the idealized bathymetry and initial-temperature profiles,
used by both the z-star and p-star init steps.
"""

import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.coriolis import add_coriolis_to_dataset
from polaris.mesh.planar import compute_planar_hex_nx_ny


def build_overflow_mesh(step):
    """
    Build the overflow planar hex mesh, cull it, and add the Coriolis
    parameter, writing out ``base_mesh.nc``, ``culled_mesh.nc`` and
    ``culled_graph.info``.

    Parameters
    ----------
    step : polaris.ocean.model.OceanIOStep
        The init step the mesh is built for, used for its config, logger
        and model-aware dataset output methods.

    Returns
    -------
    xarray.Dataset
        The culled mesh dataset.
    """
    config = step.config
    logger = step.logger

    section = config['overflow']
    lx = section.getfloat('lx')
    ly = section.getfloat('ly')
    resolution = section.getfloat('resolution')

    nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
    dc = 1e3 * resolution
    ds_mesh = make_planar_hex_mesh(
        nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=False
    )
    step.write_model_dataset(ds_mesh, 'base_mesh.nc', config)

    ds_mesh = cull(ds_mesh, logger=logger)
    ds_mesh = convert(
        ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
    )
    ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
    step.write_horiz_mesh_dataset(ds_mesh, 'culled_mesh.nc', config)
    return ds_mesh


def compute_bottom_depth(config, x_cell):
    """
    Compute the overflow continental shelf-like bathymetry, a tanh
    profile between the shelf depth and the maximum bottom depth.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[overflow]`` geometry options.

    x_cell : xarray.DataArray
        The x-coordinates of the cells (m) with dimension ``nCells``.

    Returns
    -------
    xarray.DataArray
        The positive-down bottom depth (m) with dimension ``nCells``.
    """
    section = config['overflow']
    max_bottom_depth = section.getfloat('max_bottom_depth')
    shelf_depth = section.getfloat('shelf_depth')
    x_slope = section.getfloat('x_slope')
    l_slope = section.getfloat('l_slope')

    bottom_depth = shelf_depth + 0.5 * (max_bottom_depth - shelf_depth) * (
        1.0
        + np.tanh(
            (x_cell - x_cell.min() - x_slope * 1.0e3) / (l_slope * 1.0e3)
        )
    )
    return bottom_depth


def compute_initial_temperature(config, x_cell):
    """
    Compute the overflow initial temperature, constant except for a
    block of cold water on the shelf.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[overflow]`` initial-condition options.

    x_cell : xarray.DataArray
        The x-coordinates of the cells (m) with dimension ``nCells``.

    Returns
    -------
    xarray.DataArray
        The temperature (degC) with dimension ``nCells``.
    """
    section = config['overflow']
    x_dense = section.getfloat('x_dense')
    lower_temperature = section.getfloat('lower_temperature')
    higher_temperature = section.getfloat('higher_temperature')

    temperature = xr.where(
        (x_cell - x_cell.min()) < x_dense * 1.0e3,
        lower_temperature,
        higher_temperature,
    )
    return temperature
