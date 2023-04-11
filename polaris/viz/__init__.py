import importlib.resources as imp_res  # noqa: F401
import os

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.collections import PatchCollection
from matplotlib.colors import LogNorm
from matplotlib.patches import Polygon


def plot_horiz_field(config, ds, dsMesh, fieldName, outFileName,
                     title=None, tIndex=None, zIndex=None,
                     vmin=None, vmax=None, show_patch_edges=False,
                     cmap=None, cmap_set_under=None, cmap_scale='linear'):

    """
    Plot a horizontal field from a planar domain using x,y coordinates at a
    single time and depth slice.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid

    ds : xarray.Dataset
        A data set containing fieldName

    dsMesh : xarray.Dataset
        A data set containing mesh variables

    fieldName: str
        The name of the variable to plot, which must be present in ds

    outFileName: str
        The path to which the plot image should be written

    title: str, optional
        The title of the plot

    vmin, vmax : float, optional
        The minimum and maximum values for the colorbar

    show_patch_edges : boolean, optional
        If true, patches will be plotted with visible edges

    tIndex, zIndex: int, optional
        The indices of 'Time' and 'nVertLevels' axes to select for plotting

    cmap : Colormap or str, optional
        A color map to plot

    cmap_set_under : str or None, optional
        A color for low out-of-range values

    cmap_scale : {'log', 'linear'}, optional
        Whether the colormap is logarithmic or linear
    """
    style_filename = str(
        imp_res.files('polaris.viz') / 'polaris.mplstyle')
    plt.style.use(style_filename)

    try:
        os.makedirs(os.path.dirname(outFileName))
    except OSError:
        pass

    if title is None:
        title = fieldName

    if 'maxLevelCell' not in dsMesh:
        raise ValueError(
            'maxLevelCell must be added to dsMesh before plotting.')
    if fieldName not in ds:
        raise ValueError(f'{fieldName} must be present in ds before plotting.')

    field = ds[fieldName]

    if 'Time' in field.dims and tIndex is None:
        tIndex = 0
    if tIndex is not None:
        field = field[tIndex, :]
    if 'nVertLevels' in field.dims:
        zIndex = 0
    if zIndex is not None:
        field = field[:, zIndex]

    if 'nCells' in field.dims:
        oceanMask = dsMesh.maxLevelCell - 1 >= 0
        oceanMask = _remove_boundary_cells_from_mask(dsMesh, oceanMask)
        oceanPatches = _compute_cell_patches(dsMesh, oceanMask)
    elif 'nEdges' in field.dims:
        oceanMask = np.ones_like(field, dtype='bool')
        oceanMask = _remove_boundary_edges_from_mask(dsMesh, oceanMask)
        oceanPatches = _compute_edge_patches(dsMesh, oceanMask)
    oceanPatches.set_array(field[oceanMask])
    if cmap is not None:
        oceanPatches.set_cmap(cmap)
    if cmap_set_under is not None:
        current_cmap = oceanPatches.get_cmap()
        current_cmap.set_under(cmap_set_under)

    if show_patch_edges:
        oceanPatches.set_edgecolor('black')
    else:
        oceanPatches.set_edgecolor('face')
    oceanPatches.set_clim(vmin=vmin, vmax=vmax)

    if cmap_scale == 'log':
        oceanPatches.set_norm(LogNorm(vmin=max(1e-10, vmin),
                              vmax=vmax, clip=False))

    width = dsMesh.xCell.max() - dsMesh.xCell.min()
    length = dsMesh.yCell.max() - dsMesh.yCell.min()
    aspect_ratio = width.values / length.values
    fig_width = 4
    legend_width = fig_width / 5
    figsize = (fig_width + legend_width, fig_width / aspect_ratio)

    plt.figure(figsize=figsize)
    ax = plt.subplot(111)
    ax.add_collection(oceanPatches)
    ax.set_xlabel('x (km)')
    ax.set_ylabel('y (km)')
    ax.set_aspect('equal')
    ax.autoscale(tight=True)
    plt.colorbar(oceanPatches, extend='both', shrink=0.7)
    plt.title(title)
    plt.tight_layout(pad=0.5)
    plt.savefig(outFileName)
    plt.close()


def _remove_boundary_cells_from_mask(dsMesh, mask):
    areaCell = dsMesh.areaCell.values
    nVerticesOnCell = dsMesh.nEdgesOnCell.values
    verticesOnCell = dsMesh.verticesOnCell.values - 1
    xVertex = dsMesh.xVertex.values
    yVertex = dsMesh.yVertex.values
    for iCell in range(dsMesh.sizes['nCells']):
        if not mask[iCell]:
            continue
        nVert = nVerticesOnCell[iCell]
        vertexIndices = verticesOnCell[iCell, :nVert]

        # Remove cells that span the periodic boundaries
        dx = max(xVertex[vertexIndices]) - min(xVertex[vertexIndices])
        dy = max(yVertex[vertexIndices]) - min(yVertex[vertexIndices])
        if dx * dy / 10 > areaCell[iCell]:
            mask[iCell] = 0

    return mask


def _remove_boundary_edges_from_mask(dsMesh, mask):
    areaCell = dsMesh.areaCell.values
    cellsOnEdge = dsMesh.cellsOnEdge.values - 1
    verticesOnEdge = dsMesh.verticesOnEdge.values - 1
    xCell = dsMesh.xCell.values
    yCell = dsMesh.yCell.values
    boundaryVertex = dsMesh.boundaryVertex.values
    xVertex = dsMesh.xVertex.values
    yVertex = dsMesh.yVertex.values
    for iEdge in range(dsMesh.sizes['nEdges']):
        if not mask[iEdge]:
            continue
        cellIndices = cellsOnEdge[iEdge]
        vertexIndices = verticesOnEdge[iEdge, :]
        if any(boundaryVertex[vertexIndices]):
            mask[iEdge] = 0
        vertices = np.zeros((4, 2))
        vertices[0, 0] = xVertex[vertexIndices[0]]
        vertices[0, 1] = yVertex[vertexIndices[0]]
        vertices[1, 0] = xCell[cellIndices[0]]
        vertices[1, 1] = yCell[cellIndices[0]]
        vertices[2, 0] = xVertex[vertexIndices[1]]
        vertices[2, 1] = yVertex[vertexIndices[1]]
        vertices[3, 0] = xCell[cellIndices[1]]
        vertices[3, 1] = yCell[cellIndices[1]]

        # Remove cells that span the periodic boundaries
        dx = max(vertices[:, 0]) - min(vertices[:, 0])
        dy = max(vertices[:, 1]) - min(vertices[:, 1])
        if dx * dy / 10 > areaCell[0]:
            mask[iEdge] = 0

    return mask


def _compute_cell_patches(dsMesh, mask):
    patches = []
    nVerticesOnCell = dsMesh.nEdgesOnCell.values
    verticesOnCell = dsMesh.verticesOnCell.values - 1
    xVertex = dsMesh.xVertex.values
    yVertex = dsMesh.yVertex.values
    for iCell in range(dsMesh.sizes['nCells']):
        if not mask[iCell]:
            continue
        nVert = nVerticesOnCell[iCell]
        vertexIndices = verticesOnCell[iCell, :nVert]
        vertices = np.zeros((nVert, 2))
        vertices[:, 0] = 1e-3 * xVertex[vertexIndices]
        vertices[:, 1] = 1e-3 * yVertex[vertexIndices]

        polygon = Polygon(vertices, True)
        patches.append(polygon)

    p = PatchCollection(patches, alpha=1.)

    return p


def _compute_edge_patches(dsMesh, mask):
    patches = []
    cellsOnEdge = dsMesh.cellsOnEdge.values - 1
    verticesOnEdge = dsMesh.verticesOnEdge.values - 1
    xCell = dsMesh.xCell.values
    yCell = dsMesh.yCell.values
    xVertex = dsMesh.xVertex.values
    yVertex = dsMesh.yVertex.values
    for iEdge in range(dsMesh.sizes['nEdges']):
        if not mask[iEdge]:
            continue
        cellIndices = cellsOnEdge[iEdge]
        vertexIndices = verticesOnEdge[iEdge, :]
        vertices = np.zeros((4, 2))
        vertices[0, 0] = 1e-3 * xVertex[vertexIndices[0]]
        vertices[0, 1] = 1e-3 * yVertex[vertexIndices[0]]
        vertices[1, 0] = 1e-3 * xCell[cellIndices[0]]
        vertices[1, 1] = 1e-3 * yCell[cellIndices[0]]
        vertices[2, 0] = 1e-3 * xVertex[vertexIndices[1]]
        vertices[2, 1] = 1e-3 * yVertex[vertexIndices[1]]
        vertices[3, 0] = 1e-3 * xCell[cellIndices[1]]
        vertices[3, 1] = 1e-3 * yCell[cellIndices[1]]

        polygon = Polygon(vertices, True)
        patches.append(polygon)

    p = PatchCollection(patches, alpha=1.)

    return p
