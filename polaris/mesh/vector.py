import numpy as np
import xarray as xr


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

    vec_cell = xr.concat([ds.xCell, ds.yCell, ds.zCell], dim='R3').T
    vec_edge = xr.concat([ds.xEdge, ds.yEdge, ds.zEdge], dim='R3').T

    cell_1 = ds.cellsOnEdge.isel(TWO=0) - 1
    cell_2 = ds.cellsOnEdge.isel(TWO=1) - 1

    # assume normal points from the cell1 to cell2 valid for non-boundary edges
    normal = vec_cell.isel(nCells=cell_2) - vec_cell.isel(nCells=cell_1)

    # boundary edge: normal points from the edge location to the cell location
    normal = normal.where(
        cell_1 != -1, vec_cell.isel(nCells=cell_2) - vec_edge
    )

    # boundary edge: normal points from the cell location to the edge location
    normal = normal.where(
        cell_2 != -1, vec_edge - vec_cell.isel(nCells=cell_1)
    )

    return normal / np.linalg.norm(normal, ord=2, axis=-1, keepdims=True)
