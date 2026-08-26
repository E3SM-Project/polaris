from typing import Literal

import numpy as np
import xarray as xr

# TODO: when python 3.11 is dropped add type alias
VariableLocationType = Literal['cell', 'edge', 'vertex']


def get_coordinate_matrix(
    ds: xr.Dataset, location: VariableLocationType = 'cell'
) -> xr.DataArray:
    """
    Get the Cartesian coordinates of the mesh elements at a given location
    as a single array

    Parameters
    ----------
    ds : xr.Dataset
        MPAS mesh Dataset
    location : {'cell', 'edge', 'vertex'}, optional
        The mesh location to get the coordinates of

    Returns
    -------
    xr.DataArray (nCells or nEdges or nVertices, R3)
        The Cartesian coordinates of each element at ``location``
    """
    # e.g. "cell" -> "xCell", "vertex" -> "xVertex"
    suffix = location.capitalize()
    return xr.concat(
        [ds[f'x{suffix}'], ds[f'y{suffix}'], ds[f'z{suffix}']], dim='R3'
    ).T


def compute_edge_normal_vec(ds: xr.Dataset) -> xr.DataArray:
    """
    Compute the normal vector for each edge in a mesh

    Parameters
    ----------
    ds : xr.Dataset
        MPAS mesh Dataset

    Returns
    -------
    xr.DataArray (nEdges, R3)
        Normal vector for each edge in the mesh
    """

    periodic = ds.attrs.get('is_periodic', 'NO') == 'YES'
    if periodic:
        period = np.array([ds.attrs['x_period'], ds.attrs['y_period'], 0.0])
    else:
        # a zero period makes _fix_periodicity() a no-op, so the same
        # formulas below are correct for non-periodic meshes as well
        period = np.array([0.0, 0.0, 0.0])

    vec_cell = get_coordinate_matrix(ds, 'cell')
    vec_edge = get_coordinate_matrix(ds, 'edge')

    cell_1 = ds.cellsOnEdge.isel(TWO=0) - 1
    cell_2 = ds.cellsOnEdge.isel(TWO=1) - 1

    pos_cell_1 = vec_cell.isel(nCells=cell_1)
    pos_cell_2 = vec_cell.isel(nCells=cell_2)

    # interior edge: normal points from cell 1 to cell 2, wrapping across
    # a periodic boundary as needed
    normal = _fix_periodicity(pos_cell_2, pos_cell_1, period) - pos_cell_1

    # boundary edge (no cell 1): normal points from the edge location to
    # the cell location
    normal = normal.where(
        cell_1 != -1,
        pos_cell_2 - _fix_periodicity(vec_edge, pos_cell_2, period),
    )

    # boundary edge (no cell 2): normal points from the cell location to
    # the edge location
    normal = normal.where(
        cell_2 != -1,
        _fix_periodicity(vec_edge, pos_cell_1, period) - pos_cell_1,
    )

    return normal / np.linalg.norm(normal, ord=2, axis=-1, keepdims=True)


def _fix_periodicity(point_1, point_2, period):
    """
    Recompute location of point 1 relative to point 2 with a given period

    Implementation take from `mpas_fix_periodicity` subroutine in:
        E3SM/components/mpas-framework/src/operators/mpas_vector_operations.F
    """

    dist = point_1 - point_2
    wrapped = point_1 - np.sign(dist) * period

    return xr.where(np.absolute(dist) > period * 0.5, wrapped, point_1)
