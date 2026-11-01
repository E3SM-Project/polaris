import cmocean  # noqa: F401
import mosaic


def plot_surface_salinity(ax, ds_mesh, ds, title, vmin, vmax):
    """
    Plot the surface salinity of one snapshot on a panel of a figure, without
    a colorbar so that panels can share one

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The panel to plot on

    ds_mesh : xarray.Dataset
        The horizontal mesh

    ds : xarray.Dataset
        Model output at one time, with ``salinity``

    title : str
        The title of the panel

    vmin : float
        The lower limit of the color scale

    vmax : float
        The upper limit of the color scale

    Returns
    -------
    collection : matplotlib.collections.PolyCollection
        The plotted cells, for a shared colorbar
    """
    descriptor = mosaic.Descriptor(ds_mesh)
    collection = mosaic.polypcolor(
        ax,
        descriptor,
        ds.salinity.isel(nVertLevels=0),
        cmap='cmo.haline',
        vmin=vmin,
        vmax=vmax,
        edgecolor='face',
    )
    ax.set_aspect('equal')
    # crop to the cell centers, hiding the gaps mosaic leaves at the
    # periodic seams
    ax.set_xlim(float(ds_mesh.xCell.min()), float(ds_mesh.xCell.max()))
    ax.set_ylim(float(ds_mesh.yCell.min()), float(ds_mesh.yCell.max()))
    # ticks in kilometers
    ax.xaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
    ax.yaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
    ax.set_title(title)
    return collection
