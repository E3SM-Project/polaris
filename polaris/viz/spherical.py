import configparser
import importlib.resources as imp_res

import cartopy
import cmocean  # noqa: F401
import matplotlib.colors as cols
import matplotlib.path as mpath
import mosaic
import mosaic.utils
import numpy as np
import xarray as xr
from cartopy.geodesic import Geodesic
from matplotlib import colormaps
from matplotlib.figure import Figure
from mpas_tools.io import open_dataset
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from pyremap.descriptor.utility import interp_extrap_corner
from ruamel.yaml import YAML

from polaris.viz.helper import (
    add_fitted_suptitle,
    get_projection,
    make_room_for_gridline_labels,
)
from polaris.viz.style import mplstyle_context

# the connectivity arrays mosaic remaps when it culls a mesh, mirroring
# ``mosaic.descriptor.connectivity_arrays``
_CONNECTIVITY_ARRAYS = [
    'cellsOnEdge',
    'cellsOnVertex',
    'verticesOnEdge',
    'verticesOnCell',
    'edgesOnVertex',
]


def plot_global_mpas_field(
    da,
    out_filename,
    config,
    colormap_section,
    mesh_filename=None,
    title=None,
    dpi=None,
    plot_land=True,
    colorbar_label='',
    central_longitude=0.0,
    figsize=(8, 4.5),
    patch_edge_color=None,
    descriptor=None,
    projection_name='PlateCarree',
    cell_indices=None,
    ds_transect=None,
    enforce_aspect_ratio=False,
    extent=None,
    circular_boundary=False,
):
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

    descriptor : mosaic.Descriptor, optional
        Descriptor from a previous call to ``plot_global_mpas_field()``

    projection_name : str, optional
        Name of the projection supported by mosaic

    cell_indices : integer array, optional
        Indices corresponding to which cells in the array to plot

    ds_transect : xr.Dataset, optional
        Transect dataset produced by mpas_tools which will be traced on the
        global field

    enforce_aspect_ratio : logical, optional
        Whether to enforce the aspect ratio of the figure according to lat,
        lon bounds

    extent : tuple of float, optional
        The ``(lon_min, lon_max, lat_min, lat_max)`` the map covers, in
        degrees.  The map is scaled to the data being plotted if this is not
        given.

    circular_boundary : bool, optional
        Whether to clip the map to a circle inscribed in the axes, which is
        how a polar stereographic map of everything poleward of some latitude
        is drawn.  Meaningless without ``extent``

    Returns
    -------
    descriptor : mosaic.Descriptor
        For reuse with future plots. Patches are cached, so the Descriptor only
        needs to be created once per mesh file.
    """

    with mplstyle_context(dpi=dpi):
        transform = cartopy.crs.Geodetic()
        projection = get_projection(
            projection_name, central_longitude=central_longitude
        )

        if descriptor is None:
            if mesh_filename is None:
                raise ValueError(
                    'Either mesh_filename or descriptor must be given'
                    ' as parameters to Descriptor'
                )
            mesh_ds = open_dataset(mesh_filename)
            model = config.get('ocean', 'model')
            if model == 'omega':
                package = 'polaris.ocean.model'
                filename = 'mpaso_to_omega.yaml'
                text = imp_res.files(package).joinpath(filename).read_text()
                yaml_data = YAML(typ='rt')
                nested_dict = yaml_data.load(text)
                mpaso_to_omega_dim_map = nested_dict['dimensions']
                mpaso_to_omega_var_map = nested_dict['variables']
                # map Omega dimension and variable names back to their
                # MPAS-Ocean equivalents
                rename = {
                    omega_dim: mpaso_dim
                    for mpaso_dim, omega_dim in mpaso_to_omega_dim_map.items()
                    if omega_dim in mesh_ds.dims
                }
                rename.update(
                    {
                        omega_var: mpaso_var
                        for mpaso_var, omega_var in (
                            mpaso_to_omega_var_map.items()
                        )
                        if omega_var in mesh_ds
                    }
                )
                if rename:
                    mesh_ds = mesh_ds.rename(rename)
            mesh_ds.attrs['is_periodic'] = 'NO'

            if cell_indices is not None:
                mesh_ds = _cull_mesh_to_cells(mesh_ds, cell_indices)
            descriptor = mosaic.Descriptor(
                mesh_ds,
                projection=projection,
                transform=transform,
                use_latlon=True,
            )

        fig = Figure(figsize=figsize, constrained_layout=True)
        ax = fig.add_subplot(111, projection=projection)

        if extent is not None:
            ax.set_extent(extent, crs=cartopy.crs.PlateCarree())
        if circular_boundary:
            _set_circular_boundary(ax)

        if title is not None:
            add_fitted_suptitle(fig, title)

        colormap, norm, ticks = setup_colormap(config, colormap_section)

        pcolor_kwargs = dict(
            cmap=colormap, norm=norm, zorder=1, edgecolors='face'
        )

        if patch_edge_color is not None:
            pcolor_kwargs['edgecolors'] = patch_edge_color

        gl = ax.gridlines(
            color='gray', linestyle=':', zorder=5, draw_labels=True
        )
        gl.right_labels = False
        gl.top_labels = False
        make_room_for_gridline_labels(ax)

        if plot_land:
            _add_land_lakes_coastline(ax)

        pc = mosaic.polypcolor(ax, descriptor, da, **pcolor_kwargs)

        cbar = fig.colorbar(
            pc, ax=ax, label=colorbar_label, extend='both', shrink=0.6
        )
        if ds_transect is not None:
            ax.plot(
                ds_transect.lonNode.values,
                ds_transect.latNode.values,
                '.r',
                transform=transform,
            )

        if enforce_aspect_ratio:
            min_latitude = np.rad2deg(mesh_ds.latCell.min().values)
            max_latitude = np.rad2deg(mesh_ds.latCell.max().values)
            min_longitude = np.rad2deg(mesh_ds.lonCell.min().values)
            max_longitude = np.rad2deg(mesh_ds.lonCell.max().values)
            geod = Geodesic()
            x_distance = geod.inverse(
                [min_longitude, min_latitude], [max_longitude, min_latitude]
            )[0, 0]
            y_distance = geod.inverse(
                [min_longitude, min_latitude], [min_longitude, max_latitude]
            )[0, 0]
            ax.set_aspect(y_distance / x_distance)

        if ticks is not None:
            cbar.set_ticks(ticks)
            cbar.set_ticklabels([f'{tick}' for tick in ticks])

        # Let constrained_layout manage the margins; combining it with
        # bbox_inches='tight' on a fixed-aspect GeoAxes with an
        # attached colorbar can collapse the map axes so only part of
        # the globe is drawn.
        fig.savefig(out_filename)


def plot_global_lat_lon_field(
    lon,
    lat,
    data_array,
    out_filename,
    config,
    colormap_section,
    title=None,
    plot_land=True,
    colorbar_label=None,
):
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

    with mplstyle_context():
        nlat, nlon = data_array.shape
        if lon.shape[0] == nlon:
            lon_corner = interp_extrap_corner(lon)
        elif lon.shape[0] == nlon + 1:
            lon_corner = lon
        else:
            raise ValueError(
                f'Unexpected length of lon {lon.shape[0]}. Should '
                f'be either {nlon} or {nlon + 1}'
            )

        if lat.shape[0] == nlat:
            lat_corner = interp_extrap_corner(lat)
        elif lat.shape[0] == nlat + 1:
            lat_corner = lat
        else:
            raise ValueError(
                f'Unexpected length of lat {lat.shape[0]}. Should '
                f'be either {nlat} or {nlat + 1}'
            )

        figsize = (8, 4.5)
        fig = Figure(figsize=figsize)
        if title is not None:
            add_fitted_suptitle(fig, title)

        subplots = [111]
        ref_projection = cartopy.crs.PlateCarree()
        central_longitude = 0.5 * (lon_corner[0] + lon_corner[-1])
        projection = cartopy.crs.PlateCarree(
            central_longitude=central_longitude
        )

        extent = [lon_corner[0], lon_corner[-1], lat_corner[0], lat_corner[-1]]

        colormap, norm, ticks = setup_colormap(config, colormap_section)

        ax = fig.add_subplot(subplots[0], projection=projection)

        ax.set_extent(extent, crs=ref_projection)

        gl = ax.gridlines(
            crs=ref_projection,
            color='gray',
            linestyle=':',
            zorder=5,
            draw_labels=True,
        )
        gl.right_labels = False
        gl.top_labels = False
        make_room_for_gridline_labels(ax)

        plotHandle = ax.pcolormesh(
            lon_corner,
            lat_corner,
            data_array,
            cmap=colormap,
            norm=norm,
            transform=ref_projection,
            zorder=1,
        )

        if plot_land:
            _add_land_lakes_coastline(ax)

        cax = inset_axes(
            ax,
            width='3%',
            height='60%',
            loc='center right',
            bbox_to_anchor=(0.08, 0.0, 1, 1),
            bbox_transform=ax.transAxes,
            borderpad=0,
        )

        cbar = fig.colorbar(plotHandle, cax=cax, extend='both')
        cbar.set_label(colorbar_label)
        if ticks is not None:
            cbar.set_ticks(ticks)
            cbar.set_ticklabels([f'{tick}' for tick in ticks])

        fig.savefig(out_filename, bbox_inches='tight', pad_inches=0.2)


def setup_colormap(config, colormap_section):
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

    colormap = colormaps[config.get(colormap_section, 'colormap_name')]

    section = config[colormap_section]

    norm_type = section.get('norm_type')

    kwargs = section.getnumpy('norm_args')

    norm: cols.Normalize
    if norm_type == 'symlog':
        norm = cols.SymLogNorm(**kwargs)
    elif norm_type == 'log':
        norm = cols.LogNorm(**kwargs)
    elif norm_type == 'linear':
        norm = cols.Normalize(**kwargs)
    else:
        raise ValueError(
            f'Unsupported norm type {norm_type} in section {colormap_section}'
        )

    try:
        ticks = section.getnumpy('colorbar_ticks')
    except configparser.NoOptionError:
        ticks = None

    if section.has_option('under_color'):
        under_color = section.get('under_color')
        colormap.set_under(under_color)
    if section.has_option('over_color'):
        over_color = section.get('over_color')
        colormap.set_over(over_color)

    return colormap, norm, ticks


def _set_circular_boundary(ax):
    """
    Clip a map to the circle inscribed in its axes

    A polar stereographic map of everything poleward of some latitude is a
    disc, but the axes are rectangular, so without this the corners are drawn
    too and the map reads as a box with a cap in it.

    Parameters
    ----------
    ax : cartopy.mpl.geoaxes.GeoAxes
        The map axes to clip
    """
    theta = np.linspace(0.0, 2.0 * np.pi, 100)
    vertices = np.column_stack([np.sin(theta), np.cos(theta)])
    ax.set_boundary(mpath.Path(0.5 * vertices + 0.5), transform=ax.transAxes)


def _cull_mesh_to_cells(mesh_ds, cell_indices):
    """
    Cull an MPAS mesh down to a subset of its cells

    Selecting cells with ``isel(nCells=...)`` alone leaves the edge and vertex
    dimensions at their original size and the connectivity arrays pointing at
    cells that are no longer there.  Mosaic then culls the mesh again for the
    projection, and indexes those stale arrays out of bounds.

    ``mosaic.utils.cull_mesh()`` does the job properly, but it expects
    zero-based connectivity, so the arrays are shifted into that convention
    and back again around the call.  The shift back is faithful: mosaic marks
    a neighbor it culled with ``-2`` and a land boundary with ``-1``, which
    become ``-1`` and ``0`` here and are read back as ``-2`` and ``-1`` when
    the descriptor zero-bases them again.

    Parameters
    ----------
    mesh_ds : xarray.Dataset
        An MPAS mesh, with one-based connectivity arrays

    cell_indices : integer array
        The cells to keep.  Cells are kept in mesh order, so a field plotted
        on the culled mesh must be selected the same way.

    Returns
    -------
    culled_ds : xarray.Dataset
        The mesh with only those cells, and the edges and vertices that
        touch them
    """
    culled_ds = mesh_ds.copy()
    for array_name in _CONNECTIVITY_ARRAYS:
        dim = 'n' + array_name.split('On')[0].title()
        zero_based = culled_ds[array_name] - 1
        # some meshes mark "no neighbor" with the size of the dimension
        # rather than with zero, which is out of bounds once zero-based
        culled_ds[array_name] = xr.where(
            zero_based == mesh_ds.sizes[dim], -1, zero_based
        )

    cells_to_cull = np.ones(mesh_ds.sizes['nCells'], dtype=bool)
    cells_to_cull[cell_indices] = False
    culled_ds = mosaic.utils.cull_mesh(culled_ds, cells_to_cull)

    for array_name in _CONNECTIVITY_ARRAYS:
        culled_ds[array_name] = culled_ds[array_name] + 1

    return culled_ds


def _add_land_lakes_coastline(ax, ice_shelves=True):
    land_color = cartopy.feature.COLORS['land']
    water_color = cartopy.feature.COLORS['water']
    land_50m = cartopy.feature.NaturalEarthFeature(
        'physical',
        'land',
        '50m',
        edgecolor='none',
        facecolor=land_color,
    )
    coastline_50m = cartopy.feature.NaturalEarthFeature(
        'physical',
        'land',
        '50m',
        edgecolor='brown',
        facecolor='none',
    )
    lakes_50m = cartopy.feature.NaturalEarthFeature(
        'physical',
        'lakes',
        '50m',
        edgecolor='k',
        facecolor=water_color,
    )
    ax.add_feature(land_50m, zorder=0)
    if ice_shelves:
        ice_50m = cartopy.feature.NaturalEarthFeature(
            'physical',
            'antarctic_ice_shelves_polys',
            '50m',
            edgecolor='lightblue',
            facecolor='none',
        )
        ax.add_feature(ice_50m, zorder=11)
    ax.add_feature(lakes_50m, zorder=2)
    ax.add_feature(coastline_50m, zorder=10)
