import xarray as xr


def area_for_field(ds_mesh, field):
    """
    Get the appropriate area (on cells, vertices or edges) for the given
    field

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The MPAS mesh

    field : xarray.DataArray
        The field whose dimensions determine which area to return

    Returns
    -------
    area : xarray.DataArray
        The area on cells, vertices or edges
    """
    if 'nCells' in field.dims:
        area = ds_mesh.areaCell
    elif 'nEdges' in field.dims:
        area = 0.25 * ds_mesh.dcEdge * ds_mesh.dvEdge
    elif 'nVertices' in field.dims:
        vertex_degree = ds_mesh.sizes['vertexDegree']
        area = xr.zeros_like(ds_mesh.xVertex)
        for ivert in range(vertex_degree):
            cov = ds_mesh.cellsOnVertex.isel(vertexDegree=ivert) - 1
            mask = cov >= 0
            kite_area = ds_mesh.kiteAreasOnVertex.isel(vertexDegree=ivert)
            area = area + kite_area.where(mask, other=0.)
    else:
        raise ValueError('The field does not have any of the expected '
                         'horizontal dimensions for an MPAS mesh')

    return area
