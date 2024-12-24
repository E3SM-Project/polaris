import configparser

import cartopy
import cmocean  # noqa: F401
import matplotlib.colors as cols
import matplotlib.pyplot as plt
import mosaic
import xarray as xr
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from pyremap.descriptor.utility import interp_extrap_corner

from polaris.viz.style import use_mplstyle


def plot_global_mpas_field(mesh_filename, da, out_filename, config,
                           colormap_section, title=None,
                           plot_land=True, colorbar_label='',
                           central_longitude=0., figsize=(8, 4.5),
                           dpi=200, patch_edge_color=None):
    """
    Plots a data set as a longitude-latitude map

    Parameters
    ----------
    mesh_filename : str
        A filename containing the MPAS mesh

    da : xarray.DataArray
        The horizontal field to plot

    out_filename : str
        The image file name to be written

    config : polaris.config.PolarisConfigParser
        The config options to use for colormap settings

    colormap_section : str
        The name of a section in the config options. Options must include:

        colormap_name
            The name of the colormap

        norm_type
            The norm: {'linear', 'log'}

    title : str, optional
        The subtitle of the plot

    plot_land : bool
        Whether to plot continents over the data

    colorbar_label : str, optional
        Label on the colorbar

    central_longitude : float, optional
        The longitude of the center of the plot

    figsize : tuple, optional
        The size of the figure in inches

    dpi : int, optional
        Dots per inch for the output plot

    patch_edge_color : str, optional
        The color of patch edges (if not the same as the face)
    """

    use_mplstyle()

    transform = cartopy.crs.Geodetic()
    projection = cartopy.crs.PlateCarree(central_longitude=central_longitude)

    mesh_ds = xr.open_dataset(mesh_filename)
    descriptor = mosaic.Descriptor(
        mesh_ds, projection=projection, transform=transform, use_latlon=True
    )

    fig, ax = plt.subplots(figsize=figsize,
                           constrained_layout=True,
                           subplot_kw=dict(projection=projection))

    colormap, norm, ticks = _setup_colormap(config, colormap_section)

    pcolor_kwargs = dict(
        cmap=colormap, norm=norm, zorder=1, edgecolors='face', linewidths=0.2
    )

    if patch_edge_color is not None:
        pcolor_kwargs['edgecolors'] = patch_edge_color

    gl = ax.gridlines(
        color='gray', linestyle=':', zorder=5, draw_labels=True, linewidth=0.5
    )
    gl.right_labels = False
    gl.top_labels = False

    pc = mosaic.polypcolor(ax, descriptor, da, **pcolor_kwargs)

    if plot_land:
        ax._add_land_lakes_coastline(ax)

    cbar = fig.colorbar(
        pc, ax=ax, label=colorbar_label, extend='both', shrink=0.6
    )

    if ticks is not None:
        cbar.set_ticks(ticks)
        cbar.set_ticklabels([f'{tick}' for tick in ticks])

    fig.savefig(out_filename, dpi=dpi, bbox_inches='tight', pad_inches=0.1)


def plot_global_lat_lon_field(lon, lat, data_array, out_filename, config,
                              colormap_section, title=None, plot_land=True,
                              colorbar_label=None):
    """
    Plots a data set as a longitude-latitude map

    Parameters
    ----------
    lon : numpy.ndarray
        1D longitude coordinate

    lat : numpy.ndarray
        1D latitude coordinate

    data_array : numpy.ndarray
        2D data array to plot

    out_filename : str
        The image file name to be written

    config : polaris.config.PolarisConfigParser
        The config options to use for colormap settings

    colormap_section : str
        The name of a section in the config options. Options must include:

        colormap_name
            The name of the colormap

        norm_type
            The norm: {'symlog', 'log', 'linear'}

        norm_args
            A dict of arguments to pass to the norm

        It may also include:

        colorbar_ticks
            An array of values where ticks should be placed

    title : str, optional
        The subtitle of the plot

    plot_land : bool
        Whether to plot continents over the data

    colorbar_label : str, optional
        Label on the colorbar
    """

    use_mplstyle()

    nlat, nlon = data_array.shape
    if lon.shape[0] == nlon:
        lon_corner = interp_extrap_corner(lon)
    elif lon.shape[0] == nlon + 1:
        lon_corner = lon
    else:
        raise ValueError(f'Unexpected length of lon {lon.shape[0]}. Should '
                         f'be either {nlon} or {nlon + 1}')

    if lat.shape[0] == nlat:
        lat_corner = interp_extrap_corner(lat)
    elif lat.shape[0] == nlat + 1:
        lat_corner = lat
    else:
        raise ValueError(f'Unexpected length of lat {lat.shape[0]}. Should '
                         f'be either {nlat} or {nlat + 1}')

    figsize = (8, 4.5)
    dpi = 200
    fig = plt.figure(figsize=figsize, dpi=dpi)
    if title is not None:
        fig.suptitle(title, y=0.935)

    subplots = [111]
    ref_projection = cartopy.crs.PlateCarree()
    central_longitude = 0.5 * (lon_corner[0] + lon_corner[-1])
    projection = cartopy.crs.PlateCarree(central_longitude=central_longitude)

    extent = [lon_corner[0], lon_corner[-1], lat_corner[0], lat_corner[-1]]

    colormap, norm, ticks = _setup_colormap(config, colormap_section)

    ax = plt.subplot(subplots[0], projection=projection)

    ax.set_extent(extent, crs=ref_projection)

    gl = ax.gridlines(crs=ref_projection, color='gray', linestyle=':',
                      zorder=5, draw_labels=True, linewidth=0.5)
    gl.right_labels = False
    gl.top_labels = False

    plotHandle = ax.pcolormesh(lon_corner, lat_corner, data_array,
                               cmap=colormap, norm=norm,
                               transform=ref_projection, zorder=1)

    if plot_land:
        _add_land_lakes_coastline(ax)

    cax = inset_axes(ax, width='3%', height='60%', loc='center right',
                     bbox_to_anchor=(0.08, 0., 1, 1),
                     bbox_transform=ax.transAxes, borderpad=0)

    cbar = plt.colorbar(plotHandle, cax=cax, extend='both')
    cbar.set_label(colorbar_label)
    if ticks is not None:
        cbar.set_ticks(ticks)
        cbar.set_ticklabels([f'{tick}' for tick in ticks])

    plt.savefig(out_filename, dpi='figure', bbox_inches='tight',
                pad_inches=0.2)

    plt.close()


def _setup_colormap(config, colormap_section):
    """
    Set up a colormap from the registry

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options for the test case, including a section for
        the colormap

    colormap_section : str
        The name of a section in the config options. Options must include:

        colormap_name
            The name of the colormap

        norm_type
            The norm: {'symlog', 'log', 'linear'}

        norm_args
            A dict of arguments to pass to the norm

        It may also include:

        colorbar_ticks
            An array of values where ticks should be placed

    Returns
    -------
    colormap : str
        the name of the new colormap

    norm : matplotlib.colors.Normalize
        a matplotlib norm object used to normalize the colormap

    ticks : list of float
        is an array of values where ticks should be placed
    """

    colormap = plt.get_cmap(config.get(colormap_section, 'colormap_name'))

    norm_type = config.get(colormap_section, 'norm_type')

    kwargs = config.getexpression(colormap_section, 'norm_args')

    if norm_type == 'symlog':
        norm = cols.SymLogNorm(**kwargs)
    elif norm_type == 'log':
        norm = cols.LogNorm(**kwargs)
    elif norm_type == 'linear':
        norm = cols.Normalize(**kwargs)
    else:
        raise ValueError(f'Unsupported norm type {norm_type} in section '
                         f'{colormap_section}')

    try:
        ticks = config.getexpression(colormap_section, 'colorbar_ticks',
                                     use_numpyfunc=True)
    except configparser.NoOptionError:
        ticks = None

    return colormap, norm, ticks


def _add_land_lakes_coastline(ax, ice_shelves=True):
    land_color = cartopy.feature.COLORS['land']
    water_color = cartopy.feature.COLORS['water']

    land_50m = cartopy.feature.NaturalEarthFeature(
        'physical', 'land', '50m', edgecolor='k',
        facecolor=land_color, linewidth=0.5)
    lakes_50m = cartopy.feature.NaturalEarthFeature(
        'physical', 'lakes', '50m', edgecolor='k',
        facecolor=water_color, linewidth=0.5)
    ax.add_feature(land_50m, zorder=2)
    if ice_shelves:
        ice_50m = cartopy.feature.NaturalEarthFeature(
            'physical', 'antarctic_ice_shelves_polys', '50m',
            edgecolor='k', facecolor=land_color, linewidth=0.5)
        ax.add_feature(ice_50m, zorder=3)
    ax.add_feature(lakes_50m, zorder=4)
