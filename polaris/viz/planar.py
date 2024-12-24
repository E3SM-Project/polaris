import os

import cmocean  # noqa: F401
import matplotlib
import matplotlib.pyplot as plt
import mosaic
import numpy as np
from matplotlib.colors import LogNorm

from polaris.viz.style import use_mplstyle


def plot_horiz_field(ds_mesh, field, out_file_name=None,  # noqa: C901
                     ax=None, title=None, t_index=None, z_index=None,
                     vmin=None, vmax=None, show_patch_edges=False,
                     cmap=None, cmap_set_under=None, cmap_set_over=None,
                     cmap_scale='linear', cmap_title=None, figsize=None,
                     vert_dim='nVertLevels', field_mask=None, descriptor=None,
                     transect_x=None, transect_y=None, transect_color='black',
                     transect_start='red', transect_end='green',
                     transect_linewidth=2., transect_markersize=12.):
    """
    Plot a horizontal field from a planar domain using x,y coordinates at a
    single time and depth slice.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        A data set containing horizontal mesh variables

    data_array : xarray.DataArray
        The data array to plot

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

    field_mask : xarray.DataArray, optional
        A ``bool`` mask indicating where the `data_array` is valid.

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
        raise ValueError('You must supply both transect_x and transect_y or '
                         'neither')

    use_mplstyle()

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
        pcolor_kwargs['norm'] = LogNorm(
            vmin=max(1e-10, vmin), vmax=vmax, clip=False
        )

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

    if field_mask is not None:

        if field_mask.shape != field.shape:
            raise ValueError(f"The shape of `field_mask`: {field_mask.shape} "
                             f"does match shape of `field array`: "
                             f"{field.shape} make sure both arrays are defined"
                             f" at the same location")

        if np.any(~field_mask):
            field = field.where(field_mask)

    collection = mosaic.polypcolor(ax, descriptor, field, **pcolor_kwargs)

    ax.set_xlabel('x (km)')
    ax.set_ylabel('y (km)')
    ax.set_aspect('equal')
    ax.autoscale(tight=True)
    # scale ticks to be in kilometers
    ax.xaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
    ax.yaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')

    cbar = plt.colorbar(collection, extend='both', shrink=0.7, ax=ax)
    if cmap_title is not None:
        cbar.set_label(cmap_title)

    if transect_x is not None:
        transect_x = transect_x
        transect_y = transect_y
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

    return descriptor
