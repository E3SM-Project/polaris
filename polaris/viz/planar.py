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
                     cmap_scale='linear', cmap_title=None, figsize=None):
    """
    Plot a horizontal field from a planar domain using x,y coordinates at a
    single time and depth slice.

    Parameters
    ----------
    ds : xarray.Dataset
        A data set containing fieldName

    ds_mesh : xarray.Dataset
        A data set containing horizontal mesh variables

    field_name: str
        The name of the variable to plot, which must be present in ds

    out_file_name: str
        The path to which the plot image should be written

    title: str, optional
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

    cmap_title : str
        Title for color bar

    figsize : tuple
        The width and height of the figure in inches. Default is determined
        based on the aspect ratio of the domain.
    """
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

    if 'maxLevelCell' not in ds:
        raise ValueError(
            'maxLevelCell must be added to ds before plotting.')
    if field_name not in ds:
        raise ValueError(
            f'{field_name} must be present in ds before plotting.')

    field = ds[field_name]

    if 'Time' in field.dims and t_index is None:
        t_index = 0
    if t_index is not None:
        field = field.isel(Time=t_index)
    if 'nVertLevels' in field.dims and z_index is None:
        z_index = 0
    if z_index is not None:
        field = field.isel(nVertLevels=z_index)

    if 'nCells' in field.dims:
        ocean_mask = ds.maxLevelCell - 1 >= 0
        ocean_patches, ocean_mask = _compute_cell_patches(ds_mesh, ocean_mask)
    elif 'nEdges' in field.dims:
        ocean_mask = np.ones_like(field, dtype='bool')
        ocean_mask = _remove_boundary_edges_from_mask(ds_mesh, ocean_mask)
        ocean_patches, ocean_mask = _compute_edge_patches(ds_mesh, ocean_mask)
    ocean_patches.set_array(field[ocean_mask])
    if cmap is not None:
        ocean_patches.set_cmap(cmap)
    if cmap_set_under is not None:
        current_cmap = ocean_patches.get_cmap()
        current_cmap.set_under(cmap_set_under)
    if cmap_set_over is not None:
        current_cmap = ocean_patches.get_cmap()
        current_cmap.set_over(cmap_set_over)

    if show_patch_edges:
        ocean_patches.set_edgecolor('black')
    else:
        ocean_patches.set_edgecolor('face')
    ocean_patches.set_clim(vmin=vmin, vmax=vmax)

    if cmap_scale == 'log':
        ocean_patches.set_norm(LogNorm(vmin=max(1e-10, vmin),
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
    ax.add_collection(ocean_patches)
    ax.set_xlabel('x (km)')
    ax.set_ylabel('y (km)')
    ax.set_aspect('equal')
    ax.autoscale(tight=True)
    cbar = plt.colorbar(ocean_patches, extend='both', shrink=0.7, ax=ax)
    if cmap_title is not None:
        cbar.set_label(cmap_title)
    if create_fig:
        plt.title(title)
        plt.tight_layout(pad=0.5)
        plt.savefig(out_file_name)
        plt.close()


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

    p = PatchCollection(patches, alpha=1.)

    return p, mask


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

    p = PatchCollection(patches, alpha=1.)

    return p, mask
