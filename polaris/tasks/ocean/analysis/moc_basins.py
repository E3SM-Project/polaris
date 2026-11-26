"""
The overturning streamfunction of each ocean basin, computed offline from the
climatology of the simulation's monthly means.

Omega computes the global streamfunction in situ but cannot yet read the
masks a basin needs, so a basin's overturning is computed here.  Each line of
latitude in a basin is the set of edges whose two cells are both in the basin
and on either side of the latitude.  The transport across those edges, from
the climatological normal transport velocity and pseudo-thickness, is
integrated up from the sea floor to fixed elevations with each edge's own
climatological layer interfaces (see
:py:func:`polaris.ocean.overturning.compute_overturning_from_edge_transport`).

The fields come from the shared climatology the maps are plotted from, so the
basins add three variables to a pass over the monthly means that already runs
rather than making a pass of their own.  A streamfunction of climatological
means leaves out how the interfaces move from month to month and how velocity
and thickness vary together across months.  In z-star both come only from the
sea surface height, so the difference is small; layers that tilt under ice
shelves do not tilt differently from month to month, so the climatological
interfaces still hold the tilt.
"""

import numpy as np
import xarray as xr

from polaris.ocean.overturning import (
    compute_line_edge_interfaces,
    compute_line_transport,
    compute_overturning_from_edge_transport,
    get_latitude_edges,
    get_line_edge_level_range,
)
from polaris.tasks.mesh.spherical.feature_masks.moc import MOC_MASK_GROUP

# The suffix geometric_features gives each basin of the MOC Basins group,
# which the config options leave off
REGION_SUFFIX = '_MOC'

# The climatology fields a basin's streamfunction is computed from, under
# their MPAS-Ocean names.  The transport velocity is the normal velocity plus
# any eddy-induced velocity, which is what carries pseudo-thickness, and
# pseudo-thickness is what Omega's continuity equation transports, so the
# streamfunction is a mass transport divided by the reference density.
TRANSPORT_VELOCITY = 'normalTransportVelocity'
THICKNESS = 'PseudoThickness'
INTERFACES = 'GeomZInterface'
BASIN_FIELDS = [TRANSPORT_VELOCITY, THICKNESS, INTERFACES]

# The mesh fields the lines of latitude are found from
MESH_FIELDS = ['cellsOnEdge', 'latCell', 'lonCell', 'dvEdge', 'dcEdge']

# The streamfunction is computed and plotted in Sverdrups
M3_S_PER_SV = 1.0e6


def get_moc_regions(config):
    """
    Get the basins whose overturning is computed offline

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    Returns
    -------
    regions : list of str
        The basin names, as ``geometric_features`` names them without the
        ``_MOC`` suffix, e.g. ``Atlantic``
    """
    regions = config.getlist('ocean_analysis_moc', 'regions')
    regions = [region for region in regions if region]
    if len(set(regions)) != len(regions):
        raise ValueError(
            f'[ocean_analysis_moc] regions lists a basin more than once: '
            f'{", ".join(regions)}'
        )
    return regions


def get_moc_latitudes(config):
    """
    Get the latitudes of the lines the offline streamfunction is computed
    across

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    Returns
    -------
    lat : numpy.ndarray
        The latitudes (degrees north), every ``dlat`` from the South Pole to
        the North Pole
    """
    dlat = config.getfloat('ocean_analysis_moc', 'dlat')
    if dlat <= 0.0 or dlat > 180.0:
        raise ValueError(
            f'[ocean_analysis_moc] dlat must be between 0 and 180 degrees, '
            f'not {dlat}'
        )
    count = int(np.floor(180.0 / dlat + 1.0e-9))
    return -90.0 + dlat * np.arange(count + 1)


def get_moc_elevations(config, max_depth):
    """
    Get the elevations the offline streamfunction is computed at

    The elevations go down from the sea surface every
    ``elevation_spacing[0]`` m to ``spacing_break_depths[0]``, then every
    ``elevation_spacing[1]`` m, and so on, to the first elevation at or
    below the deepest sea floor.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    max_depth : float
        The depth (m, positive down) of the deepest sea floor

    Returns
    -------
    z : numpy.ndarray
        The elevations (m, positive up), from 0 downward
    """
    spacings, breaks = _get_elevation_spacing(config)
    depths = [0.0]
    depth = 0.0
    while depth < max_depth:
        index = int(np.searchsorted(breaks, depth, side='right'))
        depth = min(
            depth + spacings[index],
            breaks[index] if index < len(breaks) else np.inf,
        )
        depths.append(depth)
    return -np.asarray(depths)


def check_moc_basin_options(config):
    """
    Check the options of the offline basins, so that a bad one is reported
    at setup rather than after the climatology has been computed

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis
    """
    get_moc_regions(config)
    get_moc_latitudes(config)
    _get_elevation_spacing(config)


def get_moc_basin_masks(ds_masks, regions):
    """
    Get the cell mask of each basin, found by name

    The region dimension is whichever dimension of the mask is not the cell
    dimension, so that nothing here depends on what the mask file calls it.

    Parameters
    ----------
    ds_masks : xarray.Dataset
        The ``regionCellMasks`` and ``regionNames`` of the ``MOC Basins``
        masks, with MPAS-Ocean dimension names

    regions : list of str
        The basins, without the ``_MOC`` suffix

    Returns
    -------
    masks : dict of numpy.ndarray
        A boolean mask on cells for each basin, keyed by its name, in the
        order of ``regions``
    """
    masks = ds_masks.regionCellMasks
    region_dims = [dim for dim in masks.dims if dim != 'nCells']
    if len(region_dims) != 1:
        raise ValueError(
            f'The basin masks have dimensions {masks.dims}, not the cell '
            f'dimension and one region dimension.'
        )
    region_dim = region_dims[0]
    names = [_decode(name) for name in ds_masks.regionNames.values]
    available = [
        name[: -len(REGION_SUFFIX)]
        for name in names
        if name.endswith(REGION_SUFFIX)
    ]
    result = {}
    for region in regions:
        full_name = f'{region}{REGION_SUFFIX}'
        if full_name not in names:
            raise ValueError(
                f'[ocean_analysis_moc] regions asks for {region}, which is '
                f'not one of the {MOC_MASK_GROUP} masks: '
                f'{", ".join(available)}.'
            )
        index = names.index(full_name)
        mask = masks.isel({region_dim: index}).values
        result[region] = mask.astype(bool)
    return result


def get_basin_lines(
    ds_mesh, masks, lat, min_level_cell, max_level_cell, log=None
):
    """
    Find the edges each basin's lines of latitude cross, and the layers that
    are valid on each

    They depend only on the mesh and the masks, so they are found once and
    used for every climatology.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh, with MPAS-Ocean names

    masks : dict of numpy.ndarray
        The cell mask of each basin, keyed by the basin's name

    lat : numpy.ndarray
        The latitudes of the lines (degrees north)

    min_level_cell, max_level_cell : xarray.DataArray
        The zero-based index of the topmost and bottommost valid layer of
        each column

    log : callable, optional
        Where to report how many edges each basin's lines cross

    Returns
    -------
    lines : dict of dict
        For each basin, keyed by its name, the ``line`` edges from
        :py:func:`polaris.ocean.overturning.get_latitude_edges` and the
        ``min_level`` and ``max_level`` valid on each edge
    """
    lines = {}
    for region, mask in masks.items():
        line = get_latitude_edges(ds_mesh, lat, cell_mask=mask)
        min_level, max_level = get_line_edge_level_range(
            line, min_level_cell, max_level_cell
        )
        if log is not None:
            log(
                f'  {region}: {line.sizes["nLineEdges"]} edge crossings on '
                f'{int(np.count_nonzero(line.length.values))} lines'
            )
        lines[region] = dict(
            line=line, min_level=min_level, max_level=max_level
        )
    return lines


def compute_basin_streamfunctions(ds, lines, lat, z):
    """
    Compute the streamfunction of each basin from one climatology

    Parameters
    ----------
    ds : xarray.Dataset
        The climatological ``normalTransportVelocity``, ``PseudoThickness``
        and ``GeomZInterface``, with MPAS-Ocean names and no time dimension

    lines : dict of dict
        The edges each basin's lines cross, from :py:func:`get_basin_lines`

    lat : numpy.ndarray
        The latitudes of the lines (degrees north)

    z : numpy.ndarray
        The elevations (m, positive up), from the top down

    Returns
    -------
    streamfunction : xarray.DataArray
        The streamfunction (Sv) on ``nRegions``, ``nLatitudes`` and
        ``nElevations``, in the order of ``lines``, NaN below the deepest
        water each line crosses
    """
    streamfunctions = [
        _basin_streamfunction(ds, lat=lat, z=z, **basin)
        for basin in lines.values()
    ]
    da = xr.concat(streamfunctions, dim='nRegions')
    return da.transpose('nRegions', 'nLatitudes', 'nElevations')


def _basin_streamfunction(ds, line, min_level, max_level, lat, z):
    """
    Compute one basin's streamfunction (Sv) on latitude and elevation, masked
    below the deepest water each line crosses
    """
    n_lines = len(lat)
    velocity = ds[TRANSPORT_VELOCITY]
    level = xr.DataArray(
        np.arange(velocity.sizes['nVertLevels']), dims=('nVertLevels',)
    )
    valid = np.logical_and(level >= min_level, level <= max_level)
    transport = compute_line_transport(line, velocity, ds[THICKNESS])
    transport = transport.where(valid, 0.0)

    z_top, z_bottom = compute_line_edge_interfaces(
        line, ds[INTERFACES], min_level, max_level
    )
    psi = compute_overturning_from_edge_transport(
        transport,
        z_top,
        z_bottom,
        z,
        line_index=line.lineIndex,
        n_lines=n_lines,
    )

    # below the deepest water a line crosses is not ocean, so it is masked
    # rather than plotted as a zero streamfunction
    has_layers = (max_level >= min_level).values
    bottom = np.full(n_lines, np.inf)
    np.minimum.at(
        bottom,
        line.lineIndex.values[has_layers],
        z_bottom.values[has_layers, -1],
    )
    below = z[np.newaxis, :] < bottom[:, np.newaxis]
    values = np.where(below, np.nan, psi.values / M3_S_PER_SV)
    return xr.DataArray(values, dims=('nLatitudes', 'nElevations'))


def _get_elevation_spacing(config):
    """
    Get the spacing of the elevations and the depths where it changes
    """
    section = config['ocean_analysis_moc']
    spacings = [float(value) for value in section.getlist('elevation_spacing')]
    breaks = [
        float(value)
        for value in section.getlist('spacing_break_depths')
        if str(value).strip()
    ]
    if len(spacings) != len(breaks) + 1:
        raise ValueError(
            f'[ocean_analysis_moc] needs one more elevation_spacing than '
            f'spacing_break_depths, not {len(spacings)} and {len(breaks)}.'
        )
    if any(value <= 0.0 for value in spacings):
        raise ValueError(
            '[ocean_analysis_moc] elevation_spacing must all be positive.'
        )
    if any(value <= 0.0 for value in breaks) or np.any(np.diff(breaks) <= 0):
        raise ValueError(
            '[ocean_analysis_moc] spacing_break_depths must be positive and '
            'increasing.'
        )
    return spacings, breaks


def _decode(name):
    """A region name as a string, whether the file holds bytes or not"""
    if isinstance(name, bytes):
        return name.decode('utf-8').strip()
    return str(name).strip()
