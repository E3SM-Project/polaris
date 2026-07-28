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

    periodic = ds.attrs['is_periodic'].lower() == 'yes'
    if periodic:
        period = np.array([ds.attrs['x_period'], ds.attrs['y_period'], 0.0])
    else:
        # a zero period makes _fix_periodicity() a no-op, so the same
        # formulas below are correct for non-periodic meshes as well
        period = np.array([0.0, 0.0, 0.0])

    # concatenating along a new R3 dim leaves it chunked into one chunk
    # per input array; force it back to a single chunk so it can be used
    # as a core dimension in apply_ufunc(dask='parallelized', ...) calls
    vec_cell = xr.concat([ds.xCell, ds.yCell, ds.zCell], dim='R3').T.chunk(
        {'R3': -1}
    )
    vec_edge = xr.concat([ds.xEdge, ds.yEdge, ds.zEdge], dim='R3').T.chunk(
        {'R3': -1}
    )

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
