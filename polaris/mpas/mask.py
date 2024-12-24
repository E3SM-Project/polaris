
def cell_mask_2_edge_mask(ds_mesh, cell_mask):
    """Convert a cell mask to edge mask using mesh connectivity information

    True corresponds to valid cells and False are invalid cells

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The MPAS mesh

    cell_mask : xarray.DataArray
        The cell mask we want to convert to an edge mask


    Returns
    -------
    edge_mask : xarray.DataArray
        The edge mask corresponding to the input cell mask
    """

    # test if any are False
    if ~cell_mask.any():
        return ds_mesh.nEdges > -1

    # zero index the connectivity array
    cellsOnEdge = (ds_mesh.cellsOnEdge - 1)

    # using nCells (dim) instead of indexToCellID since it's already 0 indexed
    masked_cells = ds_mesh.nCells.where(~cell_mask, drop=True).astype(int)

    # use inverse so True/False convention matches input cell_mask
    edge_mask = ~cellsOnEdge.isin(masked_cells).any("TWO")

    return edge_mask
