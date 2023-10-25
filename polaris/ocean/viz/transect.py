import cmocean  # noqa: blah
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.tri import Triangulation
from mpas_tools.ocean.transects import (
    find_transect_levels_and_weights,
    get_outline_segments,
    interp_mpas_to_transect_triangles,
)
from mpas_tools.viz import mesh_to_triangles
from mpas_tools.viz.transects import (
    find_planar_transect_cells_and_weights,
    find_transect_cells_and_weights,
    make_triangle_tree,
)


def compute_transect(x, y, ds_3d_mesh, spherical=False):
    """
    build a sequence of triangles showing the transect intersecting mpas cells

    Parameters
    ----------
    x : xarray.DataArray
        The x or longitude coordinate of the transect

    y : xarray.DataArray
        The y or latitude coordinate of the transect

    ds_3d_mesh : xarray.Dataset
        The MPAS-Ocean mesh to use for plotting

    spherical : bool, optional
        Whether the x and y coordinates are latitude and longitude in degrees

    Returns
    -------
    ds_transect : xarray.Dataset
        The transect dataset
    """

    ds_tris = mesh_to_triangles(ds_3d_mesh)

    triangle_tree = make_triangle_tree(ds_tris)

    if spherical:
        ds_transect = find_transect_cells_and_weights(
            x, y, ds_tris, ds_3d_mesh, triangle_tree, degrees=True)
    else:
        ds_transect = find_planar_transect_cells_and_weights(
            x, y, ds_tris, ds_3d_mesh, triangle_tree)

    cell_indices = ds_transect.horizCellIndices
    mask = ds_3d_mesh.maxLevelCell.isel(nCells=cell_indices) > 0
    ds_transect = ds_transect.isel(nSegments=mask)

    ds_transect = find_transect_levels_and_weights(
        ds_transect, ds_3d_mesh.layerThickness,
        ds_3d_mesh.bottomDepth, ds_3d_mesh.maxLevelCell - 1)

    if 'landIceFraction' in ds_3d_mesh:
        interp_cell_indices = ds_transect.interpHorizCellIndices
        interp_cell_weights = ds_transect.interpHorizCellWeights
        land_ice_fraction = ds_3d_mesh.landIceFraction.isel(
            nCells=interp_cell_indices)
        land_ice_fraction = (land_ice_fraction * interp_cell_weights).sum(
            dim='nHorizWeights')
        ds_transect['landIceFraction'] = land_ice_fraction

    ds_transect['x'] = ds_transect.dNode.isel(
        nSegments=ds_transect.segmentIndices,
        nHorizBounds=ds_transect.nodeHorizBoundsIndices)

    ds_transect['z'] = ds_transect.zTransectNode

    ds_transect.compute()

    return ds_transect


def plot_transect(ds_transect, mpas_field, out_filename, title,
                  colorbar_label=None, cmap=None, figsize=(12, 6), dpi=200):
    """
    plot a transect showing the field on the MPAS-Ocean mesh and save to a file

    Parameters
    ----------
    ds_transect : xarray.Dataset
        A transect dataset from
        :py:func:`polaris.ocean.viz.compute_transect()`

    mpas_field : xarray.DataArray
        The MPAS-Ocean 3D field to plot

    out_filename : str
        The png file to write out to

    title : str
        The title of the plot

    colorbar_label : str, optional
        The colorbar label

    cmap : str, optional
        The name of a colormap to use

    figsize : tuple, optional
        The size of the figure in inches

    dpi : int, optional
        The dots per inch of the image

    """
    transect_field = interp_mpas_to_transect_triangles(ds_transect,
                                                       mpas_field)

    x_outline, z_outline = get_outline_segments(ds_transect)
    x_outline = 1e-3 * x_outline

    tri_mask = np.logical_not(transect_field.notnull().values)

    triangulation_args = _get_ds_triangulation_args(ds_transect)

    triangulation_args['mask'] = tri_mask

    tris = Triangulation(**triangulation_args)
    plt.figure(figsize=figsize)
    plt.tripcolor(tris, facecolors=transect_field.values, shading='flat',
                  cmap=cmap)
    plt.plot(x_outline, z_outline, 'k')
    if colorbar_label is not None:
        plt.colorbar(label=colorbar_label)
    plt.title(title)
    plt.xlabel('x (km)')
    plt.ylabel('z (m)')

    plt.savefig(out_filename, dpi=dpi, bbox_inches='tight', pad_inches=0.2)
    plt.close()


def _get_ds_triangulation_args(ds_transect):
    """
    get arguments for matplotlib Triangulation from triangulation dataset
    """

    n_transect_triangles = ds_transect.sizes['nTransectTriangles']
    d_node = ds_transect.dNode.isel(
        nSegments=ds_transect.segmentIndices,
        nHorizBounds=ds_transect.nodeHorizBoundsIndices)
    x = 1e-3 * d_node.values.ravel()

    z_transect_node = ds_transect.zTransectNode
    y = z_transect_node.values.ravel()

    tris = np.arange(3 * n_transect_triangles).reshape(
        (n_transect_triangles, 3))
    triangulation_args = dict(x=x, y=y, triangles=tris)

    return triangulation_args
