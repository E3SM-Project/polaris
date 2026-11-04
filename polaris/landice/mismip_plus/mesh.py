"""
The uniform planar hexagonal mesh of MISMIP+, ported from Compass
"""

import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.landice.mismip_plus.geometry import DOMAIN_LENGTH, DOMAIN_WIDTH


def get_mesh_parameters(resolution):
    """
    Get the arguments to :py:func:`mpas_tools.planar_hex.make_planar_hex_mesh`
    for a mesh with rows of cell centers exactly on the domain's walls

    The cell spacing is adjusted from the nominal resolution so that a whole,
    even number of rows spans the domain's width.  The cells span the
    domain's length plus a two-cell gutter.

    Parameters
    ----------
    resolution : float
        The nominal resolution of the mesh in km

    Returns
    -------
    nx : int
        The number of cells in the x direction

    ny : int
        The number of cells in the y direction, including a row that
        :py:func:`make_mismip_plus_mesh` culls

    dc : float
        The distance in m between adjacent cell centers
    """
    nominal_dy = 0.5 * np.sqrt(3.0) * 1.0e3 * resolution

    # make_planar_hex_mesh requires an even number of rows
    ny = 2 * int(np.ceil(0.5 * DOMAIN_WIDTH / nominal_dy))
    dc = 2.0 * (DOMAIN_WIDTH / ny) / np.sqrt(3.0)

    # one more column than spans the domain, so that the gutter is two cells
    nx = int(np.ceil(DOMAIN_LENGTH / dc)) + 1
    if DOMAIN_LENGTH % dc > 0.5 * dc:
        # the shifted rows would otherwise fall short of the calving front
        nx += 1

    # two more rows, one of which is culled, so that ny intervals between rows
    # span the width
    return nx, ny + 2, dc


def make_mismip_plus_mesh(resolution, logger):
    """
    Make the culled planar mesh of MISMIP+ in the protocol's coordinates

    The rows of cells on y = 0 and the domain's width are its walls.  MALI's
    first-order solver works on the triangulation of cell centers, so only
    the interior half of each of these cells is in the domain: their areas,
    and the lengths of the edges between them, are halved.

    Parameters
    ----------
    resolution : float
        The nominal resolution of the mesh in km

    logger : logging.Logger
        A logger for output from culling and conversion

    Returns
    -------
    ds_mesh : xarray.Dataset
        The mesh
    """
    nx, ny, dc = get_mesh_parameters(resolution)
    ds_mesh = make_planar_hex_mesh(
        nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=True
    )

    dy = 0.5 * np.sqrt(3.0) * dc

    # cull the first interior row along the top, so that the rows of cell
    # centers span exactly the domain's width
    y_max = ds_mesh.yCell.max()
    mask = np.isclose(ds_mesh.yCell, y_max - dy, atol=0.05 * dy, rtol=0.0)
    ds_mesh['cullCell'] = xr.where(mask, 1, ds_mesh.cullCell)

    ds_mesh = cull(ds_mesh, logger=logger)
    ds_mesh = convert(ds_mesh, logger=logger)

    ds_mesh = _shift_to_protocol_coordinates(ds_mesh)
    ds_mesh = _halve_wall_cells(ds_mesh, dc)
    return ds_mesh


def _shift_to_protocol_coordinates(ds_mesh):
    """
    Shift the mesh so that x starts at 0 and the channel's center is at
    half the domain's width
    """
    x_shift = -ds_mesh.xCell.min()
    y_center = 0.5 * (ds_mesh.yCell.max() + ds_mesh.yCell.min())
    y_shift = 0.5 * DOMAIN_WIDTH - y_center
    for loc in ['Cell', 'Edge', 'Vertex']:
        ds_mesh[f'x{loc}'] = ds_mesh[f'x{loc}'] + x_shift
        ds_mesh[f'y{loc}'] = ds_mesh[f'y{loc}'] + y_shift
    return ds_mesh


def _halve_wall_cells(ds_mesh, dc):
    """
    Halve the areas of the cells on the walls and the lengths of the edges
    between them, and zero the lengths of the edges outside the walls
    """
    dy = 0.5 * np.sqrt(3.0) * dc
    y_min = ds_mesh.yCell.min()
    y_max = ds_mesh.yCell.max()
    mask = np.isclose(
        ds_mesh.yCell, y_min, atol=0.05 * dy, rtol=0.0
    ) | np.isclose(ds_mesh.yCell, y_max, atol=0.05 * dy, rtol=0.0)
    ds_mesh['areaCell'] = xr.where(
        mask, 0.5 * ds_mesh.areaCell, ds_mesh.areaCell
    )

    # the distance in y between the rows of edges
    de = 0.5 * dc * np.sin(np.pi / 3.0)
    y_min = ds_mesh.yEdge.min()
    y_max = ds_mesh.yEdge.max()

    # the edges outside the walls carry no flux
    mask = np.isclose(
        ds_mesh.yEdge, y_min, atol=0.05 * de, rtol=0.0
    ) | np.isclose(ds_mesh.yEdge, y_max, atol=0.05 * de, rtol=0.0)
    ds_mesh['dvEdge'] = xr.where(mask, 0.0, ds_mesh.dvEdge)

    # the edges between cells on the walls
    mask = np.isclose(
        ds_mesh.yEdge, y_min + de, atol=0.05 * de, rtol=0.0
    ) | np.isclose(ds_mesh.yEdge, y_max - de, atol=0.05 * de, rtol=0.0)
    ds_mesh['dvEdge'] = xr.where(mask, 0.5 * ds_mesh.dvEdge, ds_mesh.dvEdge)

    return ds_mesh
