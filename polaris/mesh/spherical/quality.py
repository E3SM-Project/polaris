import numpy as np


def check_cell_polygon_quality(
    ds_mesh,
    minimum_edge_length_ratio,
    minimum_corner_sine,
    max_bad_cells_to_report,
):
    """
    Check MPAS cell polygons for nearly duplicate or collinear vertices.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        MPAS mesh dataset

    minimum_edge_length_ratio : float
        Minimum edge length as a fraction of the median edge length in each
        cell

    minimum_corner_sine : float
        Minimum sine of each corner angle in each cell

    max_bad_cells_to_report : int
        Maximum number of failing cells to include in the error message

    Returns
    -------
    diagnostics : dict
        The global minimum edge-length ratio and corner sine
    """
    required_variables = [
        'nEdgesOnCell',
        'verticesOnCell',
        'xVertex',
        'yVertex',
        'zVertex',
    ]
    for variable in required_variables:
        if variable not in ds_mesh:
            raise ValueError(f'MPAS mesh is missing variable "{variable}".')

    n_edges_on_cell = ds_mesh.nEdgesOnCell.values.astype(np.int32)
    vertices_on_cell = ds_mesh.verticesOnCell.values.astype(np.int64) - 1
    max_edges = vertices_on_cell.shape[1]

    invalid_n_edges = np.logical_or(
        n_edges_on_cell < 3, n_edges_on_cell > max_edges
    )
    if np.any(invalid_n_edges):
        bad_cell_indices = np.nonzero(invalid_n_edges)[0]
        _raise_cell_polygon_quality_error(
            reason='cells contain invalid nEdgesOnCell values',
            bad_cell_indices=bad_cell_indices,
            min_edge_length_ratio_by_cell=None,
            min_corner_sine_by_cell=None,
            minimum_edge_length_ratio=minimum_edge_length_ratio,
            minimum_corner_sine=minimum_corner_sine,
            max_bad_cells_to_report=max_bad_cells_to_report,
            ds_mesh=ds_mesh,
        )

    positions = np.arange(max_edges, dtype=np.int64)[None, :]
    valid = positions < n_edges_on_cell[:, None]

    n_vertices = ds_mesh.xVertex.size
    invalid_vertices = np.logical_and(
        valid,
        np.logical_or(vertices_on_cell < 0, vertices_on_cell >= n_vertices),
    )
    if np.any(invalid_vertices):
        bad_cell_indices = np.nonzero(np.any(invalid_vertices, axis=1))[0]
        _raise_cell_polygon_quality_error(
            reason='cells contain invalid vertex indices',
            bad_cell_indices=bad_cell_indices,
            min_edge_length_ratio_by_cell=None,
            min_corner_sine_by_cell=None,
            minimum_edge_length_ratio=minimum_edge_length_ratio,
            minimum_corner_sine=minimum_corner_sine,
            max_bad_cells_to_report=max_bad_cells_to_report,
            ds_mesh=ds_mesh,
        )

    vertices_on_cell = np.maximum(vertices_on_cell, 0)
    prev_positions = (positions - 1) % n_edges_on_cell[:, None]
    next_positions = (positions + 1) % n_edges_on_cell[:, None]
    prev_vertices = np.take_along_axis(
        vertices_on_cell, prev_positions, axis=1
    )
    next_vertices = np.take_along_axis(
        vertices_on_cell, next_positions, axis=1
    )

    vertex_coords = np.column_stack(
        [
            ds_mesh.xVertex.values,
            ds_mesh.yVertex.values,
            ds_mesh.zVertex.values,
        ]
    )

    coords = vertex_coords[vertices_on_cell]
    prev_coords = vertex_coords[prev_vertices]
    next_coords = vertex_coords[next_vertices]

    edge_lengths = np.linalg.norm(next_coords - coords, axis=2)
    edge_lengths = np.where(valid, edge_lengths, np.nan)
    cell_scale = np.nanmedian(edge_lengths, axis=1)
    edge_length_ratios = np.divide(
        edge_lengths,
        cell_scale[:, None],
        out=np.full_like(edge_lengths, np.nan),
        where=cell_scale[:, None] > 0.0,
    )

    prev_vectors = prev_coords - coords
    next_vectors = next_coords - coords
    corner_cross = np.cross(prev_vectors, next_vectors)
    corner_cross_norm = np.linalg.norm(corner_cross, axis=2)
    corner_denominator = np.linalg.norm(prev_vectors, axis=2) * np.linalg.norm(
        next_vectors, axis=2
    )
    corner_sines = np.divide(
        corner_cross_norm,
        corner_denominator,
        out=np.full_like(corner_cross_norm, np.nan),
        where=corner_denominator > 0.0,
    )
    corner_sines = np.where(valid, corner_sines, np.nan)

    min_edge_length_ratio_by_cell = np.nanmin(edge_length_ratios, axis=1)
    min_corner_sine_by_cell = np.nanmin(corner_sines, axis=1)
    bad_edge_cells = min_edge_length_ratio_by_cell < minimum_edge_length_ratio
    bad_corner_cells = min_corner_sine_by_cell < minimum_corner_sine
    bad_scale_cells = np.logical_not(np.isfinite(cell_scale)) | (
        cell_scale <= 0.0
    )
    bad_cell_indices = np.nonzero(
        bad_edge_cells | bad_corner_cells | bad_scale_cells
    )[0]

    if bad_cell_indices.size > 0:
        _raise_cell_polygon_quality_error(
            reason='cells contain degenerate or nearly degenerate polygons',
            bad_cell_indices=bad_cell_indices,
            min_edge_length_ratio_by_cell=min_edge_length_ratio_by_cell,
            min_corner_sine_by_cell=min_corner_sine_by_cell,
            minimum_edge_length_ratio=minimum_edge_length_ratio,
            minimum_corner_sine=minimum_corner_sine,
            max_bad_cells_to_report=max_bad_cells_to_report,
            ds_mesh=ds_mesh,
        )

    return {
        'minimum_edge_length_ratio': float(
            np.nanmin(min_edge_length_ratio_by_cell)
        ),
        'minimum_corner_sine': float(np.nanmin(min_corner_sine_by_cell)),
    }


def _raise_cell_polygon_quality_error(
    reason,
    bad_cell_indices,
    min_edge_length_ratio_by_cell,
    min_corner_sine_by_cell,
    minimum_edge_length_ratio,
    minimum_corner_sine,
    max_bad_cells_to_report,
    ds_mesh=None,
):
    """
    Raise a consistent error for failed cell-polygon quality checks.
    """
    # Pre-compute cell lat/lon in degrees from Cartesian coordinates if
    # available; this makes it easy to locate bad cells on a map.
    cell_latlon = None
    if ds_mesh is not None:
        have_xyz = all(v in ds_mesh for v in ('xCell', 'yCell', 'zCell'))
        if have_xyz:
            xc = ds_mesh.xCell.values
            yc = ds_mesh.yCell.values
            zc = ds_mesh.zCell.values
            cell_lat_deg = np.degrees(np.arctan2(zc, np.sqrt(xc**2 + yc**2)))
            cell_lon_deg = np.degrees(np.arctan2(yc, xc))
            cell_latlon = (cell_lat_deg, cell_lon_deg)

    report_count = min(max_bad_cells_to_report, bad_cell_indices.size)
    lines = [
        'Spherical mesh cell-polygon quality check failed: '
        f'{reason}. Found {bad_cell_indices.size} bad cells.',
        'Thresholds: '
        f'minimum_edge_length_ratio={minimum_edge_length_ratio:.3e}, '
        f'minimum_corner_sine={minimum_corner_sine:.3e}.',
        'First bad cells use 1-based MPAS cell indices:',
    ]

    for cell_index in bad_cell_indices[:report_count]:
        parts = [f'nCell={cell_index + 1}']
        if cell_latlon is not None:
            lat = cell_latlon[0][cell_index]
            lon = cell_latlon[1][cell_index]
            parts.append(f'lat={lat:.4f}deg, lon={lon:.4f}deg')
        if min_edge_length_ratio_by_cell is not None:
            parts.append(
                'min_edge_length_ratio='
                f'{min_edge_length_ratio_by_cell[cell_index]:.3e}'
            )
        if min_corner_sine_by_cell is not None:
            parts.append(
                f'min_corner_sine={min_corner_sine_by_cell[cell_index]:.3e}'
            )
        lines.append('  ' + ', '.join(parts))

    raise ValueError('\n'.join(lines))
