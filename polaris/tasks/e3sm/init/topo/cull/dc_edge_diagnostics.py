import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf


def check_ocean_dc_edge(
    ds_base_mesh,
    ocean_cull_mask,
    ds_sizing,
    min_ratio,
    max_ratio,
    min_abs_ratio,
    logger,
    out_filename='ocean_dc_edge_diagnostics.nc',
    max_clusters=10,
):
    """
    Check that ``dcEdge`` in the ocean/sea-ice domain stays within
    bounds relative to the local ocean background cell width.

    Edges whose two adjacent cells are both kept by the ocean cull mask
    (the interior edges of the future culled ocean mesh) are compared
    against the ocean background cell width sampled from the unified
    sizing field at the edge location.  A diagnostics file with the
    per-edge ratio and violation masks is written, and a ``ValueError``
    is raised if any ratio falls below ``min_ratio`` or above
    ``max_ratio``.

    See the design document ``unified_mesh_cull_leak`` in the
    documentation for the motivation and the choice of thresholds.

    Parameters
    ----------
    ds_base_mesh : xarray.Dataset
        The base MPAS mesh, with ``dcEdge``, ``latEdge``, ``lonEdge``
        and ``cellsOnEdge``

    ocean_cull_mask : xarray.DataArray or numpy.ndarray
        The ocean cull mask on base-mesh cells (1 where cells are
        culled, 0 where they are kept as ocean/sea-ice)

    ds_sizing : xarray.Dataset
        The unified sizing field, with ``ocean_background_cell_width``
        (km) on ``lat``/``lon`` coordinates (degrees)

    min_ratio : float
        The minimum allowed ratio of ``dcEdge`` to the *local* ocean
        background cell width.  This guards against land/river resolution
        leaking into the ocean, which shows up as a locally anomalous
        ratio.

    max_ratio : float
        The maximum allowed ratio of ``dcEdge`` to the local ocean
        background cell width

    min_abs_ratio : float
        The minimum allowed ratio of the *shortest* ``dcEdge`` anywhere in
        the domain to the *finest* ocean background cell width anywhere in
        it.  This is the CFL guard: the time step is set by the shortest
        edge globally, and a mesh is already sized for its finest intended
        resolution, so an edge that is short only relative to a coarse
        local background costs nothing.

    logger : logging.Logger
        The logger for summary output

    out_filename : str, optional
        The name of the diagnostics file to write

    max_clusters : int, optional
        The maximum number of violation clusters to report

    Raises
    ------
    ValueError
        If any ocean-interior edge violates the ratio bounds, or if the
        shortest edge violates the absolute bound
    """
    dc_edge = ds_base_mesh.dcEdge.values / 1e3
    lat_edge = np.degrees(ds_base_mesh.latEdge.values)
    lon_edge = np.degrees(ds_base_mesh.lonEdge.values)
    cells_on_edge = ds_base_mesh.cellsOnEdge.values

    kept = np.asarray(ocean_cull_mask) == 0

    # ocean-interior edges: both adjacent cells exist and are kept
    valid = np.all(cells_on_edge > 0, axis=1)
    cell0 = np.maximum(cells_on_edge[:, 0] - 1, 0)
    cell1 = np.maximum(cells_on_edge[:, 1] - 1, 0)
    ocean_edge = valid & kept[cell0] & kept[cell1]

    background = _sample_nearest(
        ds_sizing.ocean_background_cell_width.values,
        ds_sizing.lat.values,
        ds_sizing.lon.values,
        lat_edge,
        lon_edge,
    )

    ratio = np.full(dc_edge.shape, np.nan)
    ratio[ocean_edge] = dc_edge[ocean_edge] / background[ocean_edge]

    too_small = ocean_edge & (ratio < min_ratio)
    too_large = ocean_edge & (ratio > max_ratio)

    ds_out = xr.Dataset()
    ds_out['oceanEdgeMask'] = (
        ('nEdges',),
        ocean_edge.astype(np.int32),
    )
    ds_out['dcEdgeRatio'] = (('nEdges',), ratio)
    ds_out['dcEdgeTooSmallMask'] = (
        ('nEdges',),
        too_small.astype(np.int32),
    )
    ds_out['dcEdgeTooLargeMask'] = (
        ('nEdges',),
        too_large.astype(np.int32),
    )
    ds_out.attrs['min_dc_edge_ratio'] = min_ratio
    ds_out.attrs['max_dc_edge_ratio'] = max_ratio
    ds_out.attrs['min_dc_edge_abs_ratio'] = min_abs_ratio
    write_netcdf(ds_out, out_filename)

    n_ocean = int(ocean_edge.sum())
    if n_ocean == 0:
        logger.info('dcEdge diagnostic: no ocean-interior edges found.')
        return

    ratio_ocean = ratio[ocean_edge]
    logger.info(
        f'dcEdge diagnostic: {n_ocean} ocean-interior edges, '
        f'ratio range [{ratio_ocean.min():.3f}, {ratio_ocean.max():.3f}], '
        f'allowed [{min_ratio}, {max_ratio}].'
    )

    dc_ocean = dc_edge[ocean_edge]
    background_ocean = background[ocean_edge]
    finest_background = float(background_ocean.min())
    shortest_edge = float(dc_ocean.min())
    abs_ratio = shortest_edge / finest_background
    logger.info(
        f'dcEdge CFL guard: shortest ocean edge {shortest_edge:.3f} km '
        f'against a finest ocean background of {finest_background:.3f} km, '
        f'ratio {abs_ratio:.3f}, minimum allowed {min_abs_ratio}.'
    )

    n_small = int(too_small.sum())
    n_large = int(too_large.sum())
    if abs_ratio < min_abs_ratio:
        index = int(np.argmin(dc_ocean))
        lon = float(np.mod(lon_edge[ocean_edge][index] + 180.0, 360.0) - 180.0)
        lat = float(lat_edge[ocean_edge][index])
        message = (
            f'The shortest edge in the culled ocean/sea-ice domain is '
            f'{shortest_edge:.3f} km, only {abs_ratio:.3f} times the '
            f'{finest_background:.3f} km finest ocean background, below the '
            f'{min_abs_ratio} minimum.  This sets the forward-run time step '
            f'(see {out_filename} and the unified_mesh_dc_edge_noise design '
            f'doc).  Worst edge at lon={lon:.3f}, lat={lat:.3f}.'
        )
        logger.error(message)
        raise ValueError(message)

    if n_small == 0 and n_large == 0:
        logger.info('dcEdge diagnostic passed.')
        return

    lines = []
    for label, mask in [
        ('below min_dc_edge_ratio', too_small),
        ('above max_dc_edge_ratio', too_large),
    ]:
        count = int(mask.sum())
        if count == 0:
            continue
        lines.append(f'{count} ocean-interior edges {label}:')
        clusters = _cluster_violations(
            lat_edge[mask], lon_edge[mask], ratio[mask]
        )
        for lon, lat, n_members, worst in clusters[:max_clusters]:
            lines.append(
                f'  lon={lon:8.2f} lat={lat:7.2f} n={n_members:5d} '
                f'worst ratio={worst:.3f}'
            )

    message = (
        'The culled ocean/sea-ice domain contains edges whose dcEdge '
        'is out of bounds relative to the local ocean background cell '
        'width, indicating that resolution intended for the land/river '
        f'domain has leaked into the ocean (see {out_filename} and the '
        'unified_mesh_cull_leak design doc):\n' + '\n'.join(lines)
    )
    logger.error(message)
    raise ValueError(message)


def _sample_nearest(field, lat, lon, lat_points, lon_points):
    """
    Sample a lat/lon field at scattered points via nearest neighbor.
    """
    dlat = lat[1] - lat[0]
    dlon = lon[1] - lon[0]
    lon_points = np.mod(lon_points - lon[0], 360.0) + lon[0]
    lat_index = np.clip(
        np.round((lat_points - lat[0]) / dlat).astype(int),
        0,
        lat.size - 1,
    )
    lon_index = np.clip(
        np.round((lon_points - lon[0]) / dlon).astype(int),
        0,
        lon.size - 1,
    )
    return field[lat_index, lon_index]


def _cluster_violations(lat, lon, ratio, radius_deg=2.0):
    """
    Greedily cluster violating edges by proximity for reporting.

    Returns a list of ``(lon, lat, count, worst_ratio)`` tuples sorted
    by how far the worst member deviates from 1.
    """
    lon = np.mod(lon + 180.0, 360.0) - 180.0
    deviation = np.abs(np.log(np.maximum(ratio, 1e-10)))
    order = np.argsort(-deviation)
    assigned = np.zeros(lat.size, dtype=bool)
    clusters = []
    for index in order:
        if assigned[index]:
            continue
        dlon = np.abs(lon - lon[index])
        dlon = np.minimum(dlon, 360.0 - dlon)
        dlat = np.abs(lat - lat[index])
        members = (dlon < radius_deg) & (dlat < radius_deg) & ~assigned
        assigned[members] = True
        clusters.append(
            (
                float(lon[index]),
                float(lat[index]),
                int(members.sum()),
                float(ratio[index]),
            )
        )
    return clusters
