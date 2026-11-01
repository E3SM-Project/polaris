import os

import cmocean  # noqa: F401
import matplotlib
import mosaic
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure

from polaris.viz.style import mplstyle_context


def plot_horiz_field(  # noqa: C901
    ds_mesh,
    field,
    out_file_name=None,
    ax=None,
    title=None,
    t_index=None,
    z_index=None,
    vmin=None,
    vmax=None,
    show_patch_edges=False,
    cmap=None,
    cmap_set_under=None,
    cmap_set_over=None,
    cmap_scale='linear',
    cmap_title=None,
    figsize=None,
    vert_dim='nVertLevels',
    field_mask=None,
    descriptor=None,
    transect_x=None,
    transect_y=None,
    transect_color='black',
    transect_start='red',
    transect_end='green',
    transect_linewidth=2.0,
    transect_markersize=12.0,
):
    """
    Plot a horizontal field from a planar domain using x,y coordinates at a
    single time and depth slice.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        A data set containing horizontal mesh variables

    field : xarray.DataArray
        The data array to plot

    out_file_name : str, optional
        The path to which the plot image should be written

    ax : matplotlib.axes.Axes
        Axes to plot to if making a multi-panel figure

    title : str, optional
        The title of the plot

    vmin : float, optional
        The minimum values for the colorbar; if provided, must be positive if
        ``cmap_scale == 'log'``

    vmax : float, optional
        The maximum values for the colorbar; if provided, must be positive if
        ``cmap_scale == 'log'``

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

    field_mask : xarray.DataArray, optional
        A ``bool`` mask indicating where the ``field`` is valid.

    descriptor : mosaic.Descriptor, optional
        Descriptor from a previous call to ``plot_horiz_field()``

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
    descriptor : mosaic.Descriptor
        For reuse with future plots. Patches are cached, so the Descriptor only
        needs to be created once per mesh file.
    """
    if (transect_x is None) != (transect_y is None):
        raise ValueError(
            'You must supply both transect_x and transect_y or neither'
        )

    with mplstyle_context():
        create_fig = True
        if ax is not None:
            create_fig = False

        if create_fig:
            if out_file_name is None:
                out_file_name = f'{field.name}.png'
            try:
                os.makedirs(os.path.dirname(out_file_name))
            except OSError:
                pass

        if title is None:
            title = field.name

        if 'Time' in field.dims and t_index is None:
            t_index = 0
        if t_index is not None:
            field = field.isel(Time=t_index)
        if vert_dim in field.dims and z_index is None:
            z_index = 0
        if z_index is not None:
            field = field.isel({vert_dim: z_index})

        if descriptor is None:
            descriptor = mosaic.Descriptor(ds_mesh)

        pcolor_kwargs = dict(
            cmap=None, edgecolor='face', norm=None, vmin=vmin, vmax=vmax
        )

        if cmap is not None:
            if isinstance(cmap, str):
                cmap = matplotlib.colormaps[cmap]
            if cmap_set_under is not None:
                cmap.set_under(cmap_set_under)
            if cmap_set_over is not None:
                cmap.set_over(cmap_set_over)

            pcolor_kwargs['cmap'] = cmap

        if show_patch_edges:
            pcolor_kwargs['edgecolor'] = 'black'
            pcolor_kwargs['linewidth'] = 0.25

        if cmap_scale == 'log':
            pcolor_kwargs['norm'] = LogNorm(vmin=vmin, vmax=vmax, clip=False)
            pcolor_kwargs.pop('vmin', None)
            pcolor_kwargs.pop('vmax', None)

        if figsize is None:
            width = ds_mesh.xCell.max() - ds_mesh.xCell.min()
            length = ds_mesh.yCell.max() - ds_mesh.yCell.min()
            aspect_ratio = width.values / length.values
            fig_width = 4
            legend_width = fig_width / 5
            figsize = (fig_width + legend_width, fig_width / aspect_ratio)

        if create_fig:
            fig = Figure(figsize=figsize)
            ax = fig.add_subplot(111)
        else:
            fig = ax.get_figure()

        if field_mask is not None:
            if field_mask.shape != field.shape:
                raise ValueError(
                    f'The shape of `field_mask`: {field_mask.shape} '
                    f'does match shape of `field array`: '
                    f'{field.shape} make sure both arrays are defined'
                    f' at the same location'
                )

            if np.any(~field_mask):
                field = field.where(field_mask)

        collection = mosaic.polypcolor(ax, descriptor, field, **pcolor_kwargs)

        ax.set_xlabel('x (km)')
        ax.set_ylabel('y (km)')
        ax.set_aspect('equal')

        if descriptor.is_periodic:
            if descriptor.x_period and not descriptor.y_period:
                ax.autoscale(axis='y', tight=True)
            elif not descriptor.x_period and descriptor.y_period:
                ax.autoscale(axis='x', tight=True)
        else:
            ax.autoscale(axis='both', tight=True)

        # scale ticks to be in kilometers
        ax.xaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
        ax.yaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')

        cbar = fig.colorbar(collection, extend='both', shrink=0.7, ax=ax)
        if cmap_title is not None:
            cbar.set_label(cmap_title)

        if transect_x is not None:
            ax.plot(
                transect_x,
                transect_y,
                color=transect_color,
                linewidth=transect_linewidth,
            )
            if transect_start is not None:
                ax.plot(
                    transect_x[0],
                    transect_y[0],
                    '.',
                    color=transect_start,
                    markersize=transect_markersize,
                )
            if transect_end is not None:
                ax.plot(
                    transect_x[-1],
                    transect_y[-1],
                    '.',
                    color=transect_end,
                    markersize=transect_markersize,
                )
        if create_fig:
            ax.set_title(title)
            fig.savefig(out_file_name, bbox_inches='tight', pad_inches=0.2)

        return descriptor


def plot_mask_boundary(
    ax, ds_mesh, cell_mask, color='black', linewidth=1.0, label=None
):
    """
    Draw the boundary between cells inside and outside a mask, such as a
    grounding line or an ice front, along the edges between them

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to draw on

    ds_mesh : xarray.Dataset
        A planar mesh with ``cellsOnEdge``, ``verticesOnEdge``, ``xVertex``
        and ``yVertex``

    cell_mask : xarray.DataArray
        A ``bool`` mask on cells

    color : str, optional
        The line's color

    linewidth : float, optional
        The line's width

    label : str, optional
        The legend entry for the line
    """
    cells = ds_mesh.cellsOnEdge.values - 1
    mask = np.asarray(cell_mask.values, dtype=bool)
    interior = np.all(cells >= 0, axis=1)
    on_boundary = np.zeros(cells.shape[0], dtype=bool)
    on_boundary[interior] = (
        mask[cells[interior, 0]] != mask[cells[interior, 1]]
    )
    vertices = ds_mesh.verticesOnEdge.values[on_boundary] - 1
    x_vertex = ds_mesh.xVertex.values
    y_vertex = ds_mesh.yVertex.values
    segments = np.stack(
        [
            np.stack([x_vertex[vertices[:, 0]], y_vertex[vertices[:, 0]]], 1),
            np.stack([x_vertex[vertices[:, 1]], y_vertex[vertices[:, 1]]], 1),
        ],
        axis=1,
    )
    collection = LineCollection(
        list(segments), colors=color, linewidths=linewidth, label=label
    )
    ax.add_collection(collection)


def plot_horiz_comparison(
    ds_meshes,
    fields,
    titles,
    out_file_name,
    vmin=None,
    vmax=None,
    cmap=None,
    cmap_title=None,
    cmap_scale='linear',
    field_masks=None,
    include_difference=True,
    diff_cmap='cmo.balance',
    boundaries=None,
    suptitle=None,
    panel_size=(8.0, 2.0),
):
    """
    Plot fields from two or more runs in stacked panels with one color
    scale, and their difference if they share a mesh

    Parameters
    ----------
    ds_meshes : list of xarray.Dataset
        The planar mesh of each field.  Fields on different meshes, such as
        two resolutions, are drawn side by side without a difference.

    fields : list of xarray.DataArray
        The fields, on cells or vertices

    titles : list of str
        The title of each panel

    out_file_name : str
        The image file to write

    vmin, vmax : float, optional
        The color range of the fields, by default the range of all of them

    cmap : str, optional
        The color map of the fields

    cmap_title : str, optional
        The label of the color bars, with units

    cmap_scale : {'linear', 'log'}, optional
        The scale of the fields' color map

    field_masks : list of xarray.DataArray, optional
        Where each field is valid

    include_difference : bool, optional
        Whether to add a panel with the second field less the first, which
        needs the first two fields on the same mesh

    diff_cmap : str, optional
        The color map of the difference, centered on zero

    boundaries : list of xarray.DataArray, optional
        Cell masks whose boundaries are drawn in every panel of the same
        mesh, such as the floating ice

    suptitle : str, optional
        A title over all the panels

    panel_size : tuple of float, optional
        The width and height of each panel in inches
    """
    if field_masks is None:
        field_masks = [None] * len(fields)
    if vmin is None:
        vmin = min(float(field.min()) for field in fields)
    if vmax is None:
        vmax = max(float(field.max()) for field in fields)
    panels = list(zip(ds_meshes, fields, titles, field_masks, strict=True))
    same_mesh = ds_meshes[0] is ds_meshes[1] if len(ds_meshes) > 1 else False
    difference = None
    if include_difference and same_mesh:
        difference = fields[1] - fields[0]

    count = len(panels) + (difference is not None)
    with mplstyle_context():
        fig = Figure(figsize=(panel_size[0], panel_size[1] * count))
        axes = [fig.add_subplot(count, 1, index + 1) for index in range(count)]
        descriptors: dict = dict()
        for ax, (ds_mesh, field, title, mask) in zip(
            axes, panels, strict=False
        ):
            descriptor = descriptors.get(id(ds_mesh))
            descriptors[id(ds_mesh)] = plot_horiz_field(
                ds_mesh,
                field,
                ax=ax,
                vmin=vmin,
                vmax=vmax,
                cmap=cmap,
                cmap_scale=cmap_scale,
                cmap_title=cmap_title,
                field_mask=mask,
                descriptor=descriptor,
            )
            ax.set_title(title)
            _draw_boundaries(ax, ds_mesh, boundaries)
        if difference is not None:
            limit = float(np.nanmax(np.abs(difference.values)))
            limit = limit if limit > 0.0 else 1.0
            ax = axes[-1]
            mask = field_masks[0]
            plot_horiz_field(
                ds_meshes[0],
                difference,
                ax=ax,
                vmin=-limit,
                vmax=limit,
                cmap=diff_cmap,
                cmap_title=cmap_title,
                field_mask=mask,
                descriptor=descriptors[id(ds_meshes[0])],
            )
            ax.set_title(f'{titles[1]} minus {titles[0]}')
            _draw_boundaries(ax, ds_meshes[0], boundaries)
        if suptitle is not None:
            fig.suptitle(suptitle)
        fig.savefig(out_file_name, bbox_inches='tight', pad_inches=0.2)


def _draw_boundaries(ax, ds_mesh, boundaries):
    """Draw the boundaries of masks on the panel's mesh"""
    if boundaries is None:
        return
    for mask in boundaries:
        if mask.sizes['nCells'] == ds_mesh.sizes['nCells']:
            plot_mask_boundary(ax, ds_mesh, mask, linewidth=0.75)
