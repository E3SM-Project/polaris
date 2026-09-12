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
from matplotlib.backends.backend_agg import FigureCanvasAgg
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

# the sizing of a figure to its map settles in a few tries, and the layout
# at each size in a few passes; these are only guards against either never
# doing so
_MAX_FIT_ITERATIONS = 10
_MAX_LAYOUT_PASSES = 10


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
    fig_width=None,
    fig_height=None,
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

    fig_width : float, optional
        The width of the figure in inches.  The height is whatever leaves no
        empty canvas above and below the map, which depends on the
        projection, the extent and the title.  Defaults to 8 if neither
        ``fig_width`` nor ``fig_height`` is given.

    fig_height : float, optional
        The height of the figure in inches, as an alternative to
        ``fig_width``.  The width is then whatever leaves no empty canvas to
        either side of the map and its colorbar.

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

    enforce_aspect_ratio : bool, optional
        Whether to stretch the map so that its height and width are in the
        ratio of the geodesic distances across the mesh's latitude and
        longitude bounds

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
    if fig_width is not None and fig_height is not None:
        raise ValueError(
            'Give either fig_width or fig_height, not both: the other is '
            'set by the aspect ratio of the map'
        )
    if fig_width is None and fig_height is None:
        fig_width = 8.0

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

        # the figure is sized to the map once everything that takes up room
        # around the map has been drawn
        fig = Figure(constrained_layout=True)
        ax = fig.add_subplot(111, projection=projection)

        if extent is not None:
            ax.set_extent(extent, crs=cartopy.crs.PlateCarree())
        if circular_boundary:
            _set_circular_boundary(ax)

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
            ax.set_aspect(_geodesic_aspect_ratio(descriptor))

        if ticks is not None:
            cbar.set_ticks(ticks)
            cbar.set_ticklabels([f'{tick}' for tick in ticks])

        _fit_figure_to_map(fig, ax, cbar, title, fig_width, fig_height)

        # Let constrained_layout manage the margins; combining it with
        # bbox_inches='tight' on a fixed-aspect GeoAxes with an
        # attached colorbar can collapse the map axes so only part of
        # the globe is drawn.
        fig.savefig(out_filename)

    return descriptor


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
    figsize=(8, 4.5),
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

    figsize : tuple, optional
        The size of the figure in inches.  A size that matches the aspect
        ratio of the map leaves the least empty canvas around it
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


def _fit_figure_to_map(
    fig, ax, cbar, title, fig_width, fig_height, tolerance=0.01
):
    """
    Size a figure so that its map fills it

    A map has a fixed aspect ratio, and the layout engine centers it in
    whatever room is left once the title, the gridline labels and the
    colorbar have taken theirs, so a figure of the wrong shape has empty
    canvas above and below the map or to either side of it.  One dimension
    is fixed by the caller and the other is chosen here to leave no such
    room.

    A first guess comes from the map's aspect ratio, widened by the fraction
    of the figure the colorbar takes.  What that guess cannot know is how
    much room the layout engine gives the labels and title, since that
    depends on the font and on the projection, so the figure is then laid
    out, the room the map did not fill is trimmed, and the process repeated
    until the size settles.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure, with constrained layout

    ax : cartopy.mpl.geoaxes.GeoAxes
        The map axes, with everything already plotted on them

    cbar : matplotlib.colorbar.Colorbar
        The map's colorbar

    title : str or None
        The figure title, refitted to the figure each time its width changes

    fig_width : float or None
        The width of the figure in inches, if that is what is fixed

    fig_height : float or None
        The height of the figure in inches, if that is what is fixed

    tolerance : float, optional
        The room the map may leave empty in the free dimension, in inches
    """
    # measuring the layout needs a canvas that can produce a renderer; a
    # bare figure carries one that cannot, and savefig would attach an Agg
    # canvas anyway, so attaching it here changes nothing that is drawn
    if not hasattr(fig.canvas, 'get_renderer'):
        FigureCanvasAgg(fig)

    # the map's height over its width, in inches; a map's aspect is 'equal'
    # unless set to a number, and matplotlib stores 'equal' as 1
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    map_aspect = float(ax.get_aspect()) * abs(y1 - y0) / abs(x1 - x0)

    # the colorbar is given this fraction of the map's width plus a pad, so
    # the map gets the rest
    cbar_info = cbar.ax._colorbar_info
    map_fraction = 1.0 / (1.0 + cbar_info['fraction'] + cbar_info['pad'])

    fixed_width = fig_width is not None
    if fixed_width:
        free = map_fraction * fig_width * map_aspect
    else:
        free = fig_height / map_aspect / map_fraction

    # the layout engine reserves room for the gridline labels only where they
    # overhang the map's layout cell, and a map centered in a cell it does
    # not fill has its labels inside the cell; anchoring the map to the
    # corner the labels are on keeps them overhanging
    ax.set_anchor('SW')

    # a size at which the map falls short of its cell and one at which the
    # cell falls short of the map bracket the size wanted
    too_big = None
    too_small = None
    for _ in range(_MAX_FIT_ITERATIONS):
        if fixed_width:
            fig.set_size_inches(fig_width, free)
        else:
            fig.set_size_inches(free, fig_height)
        if title is not None:
            add_fitted_suptitle(fig, title)
        cell_width, cell_height = _settle_layout(fig, ax, tolerance)
        # how much of the room the layout engine left the map it does not
        # fill
        if fixed_width:
            slack = cell_height - cell_width * map_aspect
        else:
            slack = cell_width - cell_height / map_aspect
        if abs(slack) < tolerance:
            break
        if slack > 0.0:
            too_big = (free, slack)
        else:
            too_small = (free, slack)
        if too_big is None or too_small is None:
            # the room around the map depends only weakly on its size, so
            # trimming the slack is nearly right
            free -= slack
        else:
            # the room the layout engine reserves for a label changes
            # abruptly as the map goes from filling its cell to not, so
            # trimming the slack can overshoot; between the bracketing sizes
            # the size is taken where the line through them has no slack
            (small, small_slack), (big, big_slack) = too_small, too_big
            free = small - small_slack * (big - small) / (
                big_slack - small_slack
            )


def _settle_layout(fig, ax, tolerance):
    """
    Lay the figure out until the room left for the map stops changing

    The layout is computed from bounding boxes, without drawing the field,
    which is what takes the time.  Each pass measures the colorbar and the
    gridline labels where the previous pass put them, and where a label
    sits on a curved map boundary, where it lands depends on how big the
    map is, so a single pass does not settle the layout and the pass that
    ``savefig`` makes would differ from the one measured here.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure, with constrained layout

    ax : cartopy.mpl.geoaxes.GeoAxes
        The map axes

    tolerance : float
        The change in the map's cell, in inches, below which the layout has
        settled

    Returns
    -------
    cell_width : float
        The width of the room left for the map, in inches

    cell_height : float
        The height of the room left for the map, in inches
    """
    layout_engine = fig.get_layout_engine()
    previous = None
    for _ in range(_MAX_LAYOUT_PASSES):
        layout_engine.execute(fig)
        cell = ax.get_position(original=True)
        cell_width, cell_height = fig.get_size_inches() * (
            cell.width,
            cell.height,
        )
        if previous is not None:
            change = max(
                abs(cell_width - previous[0]), abs(cell_height - previous[1])
            )
            if change < tolerance:
                break
        previous = (cell_width, cell_height)
    return cell_width, cell_height


def _geodesic_aspect_ratio(descriptor):
    """
    The height over the width of a map of a mesh, taking the distance across
    its latitude and longitude bounds in each direction as the measure

    Parameters
    ----------
    descriptor : mosaic.Descriptor
        The descriptor of the mesh, whose cell coordinates are in the map
        projection

    Returns
    -------
    aspect_ratio : float
        The height over the width
    """
    # the descriptor keeps only the projected cell coordinates, so they are
    # taken back to longitude and latitude in degrees
    lon_lat = cartopy.crs.PlateCarree().transform_points(
        descriptor.projection,
        descriptor.ds.xCell.values,
        descriptor.ds.yCell.values,
    )
    min_longitude, min_latitude = lon_lat[:, :2].min(axis=0)
    max_longitude, max_latitude = lon_lat[:, :2].max(axis=0)
    geod = Geodesic()
    x_distance = geod.inverse(
        [min_longitude, min_latitude], [max_longitude, min_latitude]
    )[0, 0]
    y_distance = geod.inverse(
        [min_longitude, min_latitude], [min_longitude, max_latitude]
    )[0, 0]
    return y_distance / x_distance


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
