import os

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.colors import LogNorm
from matplotlib.patches import Polygon

from polaris.viz.style import use_mplstyle


def plot_horiz_field(ds, ds_mesh, field_name, out_file_name=None,  # noqa: C901
                     ax=None, title=None, t_index=None, z_index=None,
                     vmin=None, vmax=None, show_patch_edges=False,
                     cmap=None, cmap_set_under=None, cmap_set_over=None,
                     cmap_scale='linear', cmap_title=None, figsize=None,
                     vert_dim='nVertLevels', cell_mask=None, patches=None,
                     patch_mask=None, transect_x=None, transect_y=None,
                     transect_color='black', transect_start='red',
                     transect_end='green', transect_linewidth=2.,
                     transect_markersize=12.):
    """
    Plot a horizontal field from a planar domain using x,y coordinates at a
    single time and depth slice.

    Parameters
    ----------
    ds : xarray.Dataset
        A data set containing fieldName

    ds_mesh : xarray.Dataset
        A data set containing horizontal mesh variables

    field_name : str
        The name of the variable to plot, which must be present in ds

    out_file_name : str, optional
        The path to which the plot image should be written

    ax : matplotlib.axes.Axes
        Axes to plot to if making a multi-panel figure

    title : str, optional
        The title of the plot

    vmin : float, optional
        The minimum values for the colorbar

    vmax : float, optional
        The maximum values for the colorbar

    show_patch_edges : boolean, optional
        If true, patches will be plotted with visible edges

    t_index: int, optional
        The indices of ``Time`` axes to select for plotting. The default is 0
        (initial time)

    z_index: int, optional
        The indices of ``nVertLevels`` axes to select for plotting. The default
        is 0 (top level)

    cmap : Colormap or str, optional
        A color map to plot

    cmap_set_under : str or None, optional
        A color for low out-of-range values

    cmap_set_over : str or None, optional
        A color for upper out-of-range values

    cmap_scale : {'log', 'linear'}, optional
        Whether the colormap is logarithmic or linear

    cmap_title : str, optional
        Title for color bar

    figsize : tuple, optional
        The width and height of the figure in inches. Default is determined
        based on the aspect ratio of the domain.

    vert_dim : str, optional
        Name of the vertical dimension

    cell_mask : numpy.ndarray, optional
        A ``bool`` mask indicating where cells are valid, used to mask fields
        on both cells and edges. Not used if ``patches`` and ``patch_mask``
        are supplied

    patches : list of numpy.ndarray, optional
        Patches from a previous call to ``plot_horiz_field()``

    patch_mask : numpy.ndarray, optional
        A mask of where the field has patches from a previous call to
        ``plot_horiz_field()``

    transect_x : numpy.ndarray or xarray.DataArray, optional
        The x coordinates of a transect to plot on the

    transect_y : numpy.ndarray or xarray.DataArray, optional
        The y coordinates of a transect

    transect_color : str, optional
        The color of the transect line

    transect_start : str or None, optional
        The color of a dot marking the start of the transect

    transect_end : str or None, optional
        The color of a dot marking the end of the transect

    transect_linewidth : float, optional
        The width of the transect line

    transect_markersize : float, optional
        The size of the transect start and end markers

    Returns
    -------
    patches : list of numpy.ndarray
        Patches to reuse for future plots.  Patches for cells can only be
        reused for other plots on cells and similarly for edges.

    patch_mask : numpy.ndarray
        A mask used to select entries in the field that have patches
    """
    if field_name not in ds:
        raise ValueError(
            f'{field_name} must be present in ds before plotting.')

    if patches is not None:
        if patch_mask is None:
            raise ValueError('You must supply both patches and patch_mask '
                             'from a previous call to plot_horiz_field()')

    if (transect_x is None) != (transect_y is None):
        raise ValueError('You must supply both transect_x and transect_y or '
                         'neither')

    use_mplstyle()

    create_fig = True
    if ax is not None:
        create_fig = False

    if create_fig:
        if out_file_name is None:
            out_file_name = f'{field_name}.png'
        try:
            os.makedirs(os.path.dirname(out_file_name))
        except OSError:
            pass

    if title is None:
        title = field_name

    field = ds[field_name]

    if 'Time' in field.dims and t_index is None:
        t_index = 0
    if t_index is not None:
        field = field.isel(Time=t_index)
    if vert_dim in field.dims and z_index is None:
        z_index = 0
    if z_index is not None:
        field = field.isel({vert_dim: z_index})

    if patches is None:
        if cell_mask is None:
            cell_mask = np.ones_like(field, dtype='bool')
        if 'nCells' in field.dims:
            patch_mask = cell_mask
            patches, patch_mask = _compute_cell_patches(ds_mesh, patch_mask)
        elif 'nEdges' in field.dims:
            patch_mask = _edge_mask_from_cell_mask(ds_mesh, cell_mask)
            patch_mask = _remove_boundary_edges_from_mask(ds_mesh, patch_mask)
            patches, patch_mask = _compute_edge_patches(ds_mesh, patch_mask)
        else:
            raise ValueError('Cannot plot a field without dim nCells or '
                             'nEdges')
    local_patches = PatchCollection(patches, alpha=1.)
    local_patches.set_array(field[patch_mask])
    if cmap is not None:
        local_patches.set_cmap(cmap)
    if cmap_set_under is not None:
        current_cmap = local_patches.get_cmap()
        current_cmap.set_under(cmap_set_under)
    if cmap_set_over is not None:
        current_cmap = local_patches.get_cmap()
        current_cmap.set_over(cmap_set_over)

    if show_patch_edges:
        local_patches.set_edgecolor('black')
    else:
        local_patches.set_edgecolor('face')
    local_patches.set_clim(vmin=vmin, vmax=vmax)

    if cmap_scale == 'log':
        local_patches.set_norm(LogNorm(vmin=max(1e-10, vmin),
                                       vmax=vmax, clip=False))

    if figsize is None:
        width = ds_mesh.xCell.max() - ds_mesh.xCell.min()
        length = ds_mesh.yCell.max() - ds_mesh.yCell.min()
        aspect_ratio = width.values / length.values
        fig_width = 4
        legend_width = fig_width / 5
        figsize = (fig_width + legend_width, fig_width / aspect_ratio)

    if create_fig:
        plt.figure(figsize=figsize)
        ax = plt.subplot(111)
    ax.add_collection(local_patches)
    ax.set_xlabel('x (km)')
    ax.set_ylabel('y (km)')
    ax.set_aspect('equal')
    ax.autoscale(tight=True)
    cbar = plt.colorbar(local_patches, extend='both', shrink=0.7, ax=ax)
    if cmap_title is not None:
        cbar.set_label(cmap_title)

    if transect_x is not None:
        transect_x = 1e-3 * transect_x
        transect_y = 1e-3 * transect_y
        ax.plot(transect_x, transect_y, color=transect_color,
                linewidth=transect_linewidth)
        if transect_start is not None:
            ax.plot(transect_x[0], transect_y[0], '.', color=transect_start,
                    markersize=transect_markersize)
        if transect_end is not None:
            ax.plot(transect_x[-1], transect_y[-1], '.', color=transect_end,
                    markersize=transect_markersize)
    if create_fig:
        plt.title(title)
        plt.savefig(out_file_name, bbox_inches='tight', pad_inches=0.2)
        plt.close()

    return patches, patch_mask


def _edge_mask_from_cell_mask(ds, cell_mask):
    cells_on_edge = ds.cellsOnEdge - 1
    valid = cells_on_edge >= 0
    # the edge mask is True if either adjacent cell is valid and its mask is
    # True
    edge_mask = np.logical_or(
        np.logical_and(valid[:, 0], cell_mask[cells_on_edge[:, 0]]),
        np.logical_and(valid[:, 1], cell_mask[cells_on_edge[:, 1]]))
    return edge_mask


def _remove_boundary_edges_from_mask(ds, mask):
    area_cell = ds.areaCell.values
    mean_area_cell = np.mean(area_cell)
    cells_on_edge = ds.cellsOnEdge.values - 1
    vertices_on_edge = ds.verticesOnEdge.values - 1
    x_cell = ds.xCell.values
    y_cell = ds.yCell.values
    boundary_vertex = ds.boundaryVertex.values
    x_vertex = ds.xVertex.values
    y_vertex = ds.yVertex.values
    for edge_index in range(ds.sizes['nEdges']):
        if not mask[edge_index]:
            continue
        cell_indices = cells_on_edge[edge_index]
        vertex_indices = vertices_on_edge[edge_index, :]
        if any(boundary_vertex[vertex_indices]):
            mask[edge_index] = 0
            continue
        vertices = np.zeros((4, 2))
        vertices[0, 0] = x_vertex[vertex_indices[0]]
        vertices[0, 1] = y_vertex[vertex_indices[0]]
        vertices[1, 0] = x_cell[cell_indices[0]]
        vertices[1, 1] = y_cell[cell_indices[0]]
        vertices[2, 0] = x_vertex[vertex_indices[1]]
        vertices[2, 1] = y_vertex[vertex_indices[1]]
        vertices[3, 0] = x_cell[cell_indices[1]]
        vertices[3, 1] = y_cell[cell_indices[1]]

        # Remove edges that span the periodic boundaries
        dx = max(vertices[:, 0]) - min(vertices[:, 0])
        dy = max(vertices[:, 1]) - min(vertices[:, 1])
        if dx * dy / 10 > mean_area_cell:
            mask[edge_index] = 0

    return mask


def _compute_cell_patches(ds, mask):
    patches = []
    num_vertices_on_cell = ds.nEdgesOnCell.values
    vertices_on_cell = ds.verticesOnCell.values - 1
    x_vertex = ds.xVertex.values
    y_vertex = ds.yVertex.values
    area_cell = ds.areaCell.values
    for cell_index in range(ds.sizes['nCells']):
        if not mask[cell_index]:
            continue
        num_vertices = num_vertices_on_cell[cell_index]
        vertex_indices = vertices_on_cell[cell_index, :num_vertices]
        vertices = np.zeros((num_vertices, 2))
        vertices[:, 0] = 1e-3 * x_vertex[vertex_indices]
        vertices[:, 1] = 1e-3 * y_vertex[vertex_indices]

        # Remove cells that span the periodic boundaries
        dx = max(x_vertex[vertex_indices]) - min(x_vertex[vertex_indices])
        dy = max(y_vertex[vertex_indices]) - min(y_vertex[vertex_indices])
        if dx * dy / 10 > area_cell[cell_index]:
            mask[cell_index] = False
        else:
            polygon = Polygon(vertices, closed=True)
            patches.append(polygon)

    return patches, mask


def _compute_edge_patches(ds, mask):
    patches = []
    cells_on_edge = ds.cellsOnEdge.values - 1
    vertices_on_edge = ds.verticesOnEdge.values - 1
    x_cell = ds.xCell.values
    y_cell = ds.yCell.values
    x_vertex = ds.xVertex.values
    y_vertex = ds.yVertex.values
    for edge_index in range(ds.sizes['nEdges']):
        if not mask[edge_index]:
            continue
        cell_indices = cells_on_edge[edge_index]
        vertex_indices = vertices_on_edge[edge_index, :]
        vertices = np.zeros((4, 2))
        vertices[0, 0] = 1e-3 * x_vertex[vertex_indices[0]]
        vertices[0, 1] = 1e-3 * y_vertex[vertex_indices[0]]
        vertices[1, 0] = 1e-3 * x_cell[cell_indices[0]]
        vertices[1, 1] = 1e-3 * y_cell[cell_indices[0]]
        vertices[2, 0] = 1e-3 * x_vertex[vertex_indices[1]]
        vertices[2, 1] = 1e-3 * y_vertex[vertex_indices[1]]
        vertices[3, 0] = 1e-3 * x_cell[cell_indices[1]]
        vertices[3, 1] = 1e-3 * y_cell[cell_indices[1]]

        polygon = Polygon(vertices, closed=True)
        patches.append(polygon)

    return patches, mask
