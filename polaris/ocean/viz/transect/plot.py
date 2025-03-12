import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.viz.transect.vert import (
    interp_mpas_to_transect_cells,
    interp_mpas_to_transect_nodes,
)
from polaris.viz.style import use_mplstyle


def plot_transect(
    ds_transect,
    mpas_field=None,
    out_filename=None,
    ax=None,
    title=None,
    vmin=None,
    vmax=None,
    colorbar_label=None,
    cmap=None,
    figsize=(12, 6),
    dpi=200,
    method='flat',
    outline_color='black',
    ssh_color=None,
    seafloor_color=None,
    interface_color=None,
    cell_boundary_color=None,
    linewidth=1.0,
    color_start_and_end=False,
    start_color='red',
    end_color='green',
):
    """
    plot a transect showing the field on the MPAS-Ocean mesh and save to a file

    Parameters
    ----------
    ds_transect : xarray.Dataset
        A transect dataset from
        :py:func:`polaris.ocean.viz.compute_transect()`

    mpas_field : xarray.DataArray
        The MPAS-Ocean 3D field to plot

    out_filename : str, optional
        The png file to write out to

    ax : matplotlib.axes.Axes
        Axes to plot to if making a multi-panel figure

    title : str
        The title of the plot

    vmin : float, optional
        The minimum values for the colorbar

    vmax : float, optional
        The maximum values for the colorbar

    colorbar_label : str, optional
        The colorbar label, or ``None`` if no colorbar is to be included.
        Use an empty string to display a colorbar without a label.

    cmap : str, optional
        The name of a colormap to use

    figsize : tuple, optional
        The size of the figure in inches

    dpi : int, optional
        The dots per inch of the image

    method : {'flat', 'bilinear'}, optional
        The type of interpolation to use in plots.  ``flat`` means constant
        values over each MPAS cell.  ``bilinear`` means smooth interpolation
        between horizontally between cell centers and vertical between the
        middle of layers.

    outline_color : str or None, optional
        The color to use to outline the transect or ``None`` for no outline

    ssh_color : str or None, optional
        The color to use to plot the SSH (sea surface height) or ``None`` if
        not plotting the SSH (except perhaps as part of the outline)

    seafloor_color : str or None, optional
        The color to use to plot the seafloor depth or ``None`` if not plotting
        the seafloor depth (except perhaps as part of the outline)

    interface_color : str or None, optional
        The color to use to plot interfaces between layers or ``None`` if
        not plotting the layer interfaces

    cell_boundary_color : str or None, optional
        The color to use to plot vertical boundaries between cells or ``None``
        if not plotting cell boundaries.  Typically, ``cell_boundary_color``
        will be used along with ``interface_color`` to outline cells both
        horizontally and vertically.

    linewidth : float, optional
        The width of outlines, interfaces and cell boundaries

    color_start_and_end : bool, optional
        Whether to color the left and right axes of the transect, which is
        useful if the transect is also being plotted in an inset or on top of
        a horizontal field

    start_color : str, optional
        The color of left axis marking the start of the transect if
        ``plot_start_end == True``

    end_color : str, optional
        The color of right axis marking the end of the transect if
        ``plot_start_end == True``
    """

    if ax is None and out_filename is None:
        raise ValueError('One of ax or out_filename must be supplied')

    use_mplstyle()

    create_fig = ax is None
    if create_fig:
        plt.figure(figsize=figsize)
        ax = plt.subplot(111)

    z = ds_transect.zTransectNode
    x = 1e-3 * ds_transect.dNode.broadcast_like(z)

    if mpas_field is not None:
        if method == 'flat':
            transect_field = interp_mpas_to_transect_cells(
                ds_transect, mpas_field
            )
            shading = 'flat'
        elif method == 'bilinear':
            transect_field = interp_mpas_to_transect_nodes(
                ds_transect, mpas_field
            )
            shading = 'gouraud'
        else:
            raise ValueError(f'Unsupported method: {method}')

        pc = ax.pcolormesh(
            x.values,
            z.values,
            transect_field.values,
            shading=shading,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            zorder=0,
        )
        ax.autoscale(tight=True)
        if colorbar_label is not None:
            plt.colorbar(
                pc, extend='both', shrink=0.7, ax=ax, label=colorbar_label
            )

    _plot_interfaces(
        ds_transect,
        ax,
        interface_color,
        cell_boundary_color,
        ssh_color,
        seafloor_color,
        color_start_and_end,
        start_color,
        end_color,
        linewidth,
    )

    _plot_outline(x, z, ds_transect.validNodes, ax, outline_color, linewidth)

    ax.set_xlabel('transect distance (km)')
    ax.set_ylabel('z (m)')

    if create_fig:
        if title is not None:
            plt.title(title)
        plt.savefig(out_filename, dpi=dpi, bbox_inches='tight', pad_inches=0.2)
        plt.close()


def _plot_interfaces(
    ds_transect,
    ax,
    interface_color,
    cell_boundary_color,
    ssh_color,
    seafloor_color,
    color_start_and_end,
    start_color,
    end_color,
    linewidth,
):
    if cell_boundary_color is not None:
        x_bnd = 1e-3 * ds_transect.dCellBoundary.values.T
        z_bnd = ds_transect.zCellBoundary.values.T
        ax.plot(
            x_bnd,
            z_bnd,
            color=cell_boundary_color,
            linewidth=linewidth,
            zorder=1,
        )

    if interface_color is not None:
        x_int = 1e-3 * ds_transect.dInterfaceSegment.values.T
        z_int = ds_transect.zInterfaceSegment.values.T
        ax.plot(
            x_int, z_int, color=interface_color, linewidth=linewidth, zorder=2
        )

    if ssh_color is not None:
        valid = ds_transect.validNodes.any(dim='nVertNodes')
        x_ssh = 1e-3 * ds_transect.dNode.values
        z_ssh = ds_transect.ssh.where(valid).values
        ax.plot(x_ssh, z_ssh, color=ssh_color, linewidth=linewidth, zorder=4)

    if seafloor_color is not None:
        valid = ds_transect.validNodes.any(dim='nVertNodes')
        x_floor = 1e-3 * ds_transect.dNode.values
        z_floor = ds_transect.zSeafloor.where(valid).values
        ax.plot(
            x_floor,
            z_floor,
            color=seafloor_color,
            linewidth=linewidth,
            zorder=5,
        )

    if color_start_and_end:
        ax.spines['left'].set_color(start_color)
        ax.spines['left'].set_linewidth(4 * linewidth)
        ax.spines['right'].set_color(end_color)
        ax.spines['right'].set_linewidth(4 * linewidth)


def _plot_outline(
    x, z, valid_nodes, ax, outline_color, linewidth, epsilon=1e-6
):
    if outline_color is not None:
        # add a buffer of invalid values around the edge of the domain
        valid = np.zeros((x.shape[0] + 2, x.shape[1] + 2), dtype=float)
        z_buf = np.zeros(valid.shape, dtype=float)
        x_buf = np.zeros(valid.shape, dtype=float)

        valid[1:-1, 1:-1] = valid_nodes.astype(float)
        z_buf[1:-1, 1:-1] = z.values
        z_buf[0, 1:-1] = z_buf[1, 1:-1]
        z_buf[-1, 1:-1] = z_buf[-2, 1:-1]
        z_buf[:, 0] = z_buf[:, 1]
        z_buf[:, -1] = z_buf[:, -2]

        x_buf[1:-1, 1:-1] = x.values
        x_buf[0, 1:-1] = x_buf[1, 1:-1]
        x_buf[-1, 1:-1] = x_buf[-2, 1:-1]
        x_buf[:, 0] = x_buf[:, 1]
        x_buf[:, -1] = x_buf[:, -2]

        ax.contour(
            x_buf,
            z_buf,
            valid,
            levels=[1.0 - epsilon],
            colors=outline_color,
            linewidths=linewidth,
            zorder=3,
        )
