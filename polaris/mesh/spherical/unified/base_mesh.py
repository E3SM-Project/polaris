import json
import os
from typing import Any

import jigsawpy
import numpy as np
import xarray as xr
from jigsawpy.savejig import savejig
from mpas_tools.logging import check_call
from scipy.spatial import cKDTree

from polaris.constants import get_constant
from polaris.mesh import QuasiUniformSphericalMeshStep


def get_unified_background_cell_width(config):
    """
    Get a representative background ocean cell width from unified config.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config for one unified mesh

    Returns
    -------
    cell_width : float
        A representative ocean cell width in km for this mesh
    """
    section = config['sizing_field']
    return section.getfloat('ocean_background_max_km')


def get_unified_finest_cell_width(config):
    """
    Get the finest configured cell width from unified mesh settings.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config for one unified mesh

    Returns
    -------
    cell_width : float
        The smallest configured cell width in km for this mesh
    """
    section = config['sizing_field']
    widths = [
        section.getfloat('ocean_background_min_km'),
        section.getfloat('ocean_background_max_km'),
        section.getfloat('land_background_km'),
    ]

    if section.getboolean('enable_river_channel_refinement', fallback=True):
        widths.append(section.getfloat('river_channel_km'))

    widths = [width for width in widths if width is not None]
    return min(widths)


class UnifiedBaseMeshStep(QuasiUniformSphericalMeshStep):
    """
    A unified spherical mesh step with direct retained-river geometry input.
    """

    def __init__(
        self,
        component,
        sizing_field_step=None,
        river_clip_step=None,
        name='base_mesh',
        subdir=None,
        mesh_name='mesh',
    ):
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            cell_width=None,
            mesh_name=mesh_name,
        )
        self.sizing_field_step = sizing_field_step
        self.sizing_field_filename = 'sizing_field.nc'
        self.river_clip_step = river_clip_step
        self.river_network_filename = 'clipped_river_network.geojson'

    def setup(self):
        """
        Link retained-river products in addition to the sizing field.
        """
        if self.sizing_field_step is not None:
            self.add_input_file(
                filename=self.sizing_field_filename,
                work_dir_target=os.path.join(
                    self.sizing_field_step.path,
                    self.sizing_field_step.sizing_field_filename,
                ),
            )

        if self.river_clip_step is not None:
            self.add_input_file(
                filename=self.river_network_filename,
                work_dir_target=os.path.join(
                    self.river_clip_step.path,
                    self.river_clip_step.clipped_filename,
                ),
            )

        # Keep the finest configured cell width for downstream choices such as
        # source-topography resolution.
        self.cell_width = get_unified_finest_cell_width(self.config)
        super().setup()

    def build_cell_width_lat_lon(self):
        """
        Read the cell width, lon, and lat directly from sizing_field.nc.
        """
        with xr.open_dataset(self.sizing_field_filename) as ds_sizing:
            if 'cellWidth' not in ds_sizing:
                raise ValueError(
                    'Expected variable "cellWidth" in sizing_field.nc.'
                )
            if 'lat' not in ds_sizing.coords or 'lon' not in ds_sizing.coords:
                raise ValueError(
                    'Expected lat/lon coordinates in sizing_field.nc.'
                )
            cell_width = ds_sizing.cellWidth.values
            lon = ds_sizing.lon.values
            lat = ds_sizing.lat.values
        return cell_width, lon, lat

    def make_jigsaw_mesh(self, lon, lat, cell_width):
        """
        Build the JIGSAW mesh with river polylines added to the geometry.

        The sizing field remains the authoritative HFUN input. The only new
        behavior is to add retained river geometry as explicit JIGSAW line
        constraints before the standard JIGSAW-to-MPAS path runs.
        """
        logger = self.logger
        earth_radius = get_constant('mean_radius')
        opts = self.opts

        hmat = jigsawpy.jigsaw_msh_t()
        hmat.mshID = 'ELLIPSOID-GRID'
        hmat.xgrid = np.radians(lon)
        hmat.ygrid = np.radians(lat)
        hmat.value = cell_width
        jigsawpy.savemsh(opts.hfun_file, hmat)

        snap_tolerance_km = self.config.getfloat(
            'river_network',
            'base_mesh_simplify_tolerance_km',
        )
        geom = _build_unified_jigsaw_geometry(
            earth_radius=earth_radius,
            river_network_filename=self.river_network_filename,
            snap_tolerance_km=snap_tolerance_km,
        )
        jigsawpy.savemsh(opts.geom_file, geom)

        savejig(opts.jcfg_file, opts)
        check_call(['jigsaw', opts.jcfg_file], logger=logger)


def _build_unified_jigsaw_geometry(
    earth_radius,
    river_network_filename,
    snap_tolerance_km,
):
    """
    Build ellipsoid geometry with retained river polylines as constraints.
    """
    geom = jigsawpy.jigsaw_msh_t()
    geom.mshID = 'ELLIPSOID-MESH'
    geom.radii = earth_radius * 1e-3 * np.ones(3, float)

    earth_radius_km = earth_radius * 1e-3
    vert2, edge2 = _read_geojson_line_mesh(
        river_network_filename,
        snap_tolerance_km=snap_tolerance_km,
        earth_radius_km=earth_radius_km,
    )
    if vert2 is not None:
        geom.vert2 = vert2
    if edge2 is not None:
        geom.edge2 = edge2

    return geom


def _union_find(parent, x):
    """
    Return the root of x with path compression.
    """
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _merge_close_centroids(unique_rad, inverse, tol_rad):
    """
    Merge cluster centroids that are still within tol_rad of each other.

    After the first-pass union-find, some cluster centroids may still be
    closer than tol_rad (e.g. when a multi-vertex cluster centroid is
    pulled toward a neighbouring cluster). A second union-find on the
    centroid positions catches those cases.

    Parameters
    ----------
    unique_rad : numpy.ndarray, shape (n_clusters, 2)
        Centroid positions in radians from the first snapping pass.
    inverse : numpy.ndarray, shape (n_raw_vertices,)
        Maps each original raw vertex index to its first-pass cluster index.
    tol_rad : float
        Snap tolerance in radians.

    Returns
    -------
    unique_rad : numpy.ndarray, shape (n_final_clusters, 2)
        Updated centroid positions after the second-pass merge.
    inverse : numpy.ndarray, shape (n_raw_vertices,)
        Updated mapping from original raw vertices to final cluster indices.
    """
    cent_tree = cKDTree(unique_rad)
    cent_pairs = cent_tree.query_pairs(tol_rad)
    if not cent_pairs:
        return unique_rad, inverse

    n_cent = len(unique_rad)
    cent_parent = np.arange(n_cent)
    for ci, cj in cent_pairs:
        rci = _union_find(cent_parent, ci)
        rcj = _union_find(cent_parent, cj)
        if rci != rcj:
            cent_parent[rcj] = rci

    cent_roots = np.array([_union_find(cent_parent, k) for k in range(n_cent)])
    final_roots, final_inverse = np.unique(cent_roots, return_inverse=True)

    final_rad = np.zeros((len(final_roots), 2))
    final_counts = np.zeros(len(final_roots))
    np.add.at(final_rad, final_inverse, unique_rad)
    np.add.at(final_counts, final_inverse, 1)
    final_rad /= final_counts[:, None]

    return final_rad, final_inverse[inverse]


def _read_geojson_line_mesh(
    filename,
    snap_tolerance_km,
    earth_radius_km,
):
    """
    Read line features from a GeoJSON file into JIGSAW line geometry arrays.

    Vertices from different features that are closer than snap_tolerance_km
    are merged into a single vertex at their centroid.  This prevents JIGSAW
    from receiving nearly-coincident constraint points, which would otherwise
    produce degenerate triangulations and bad Voronoi polygons in the MPAS
    dual mesh.
    """
    with open(filename, encoding='utf-8') as handle:
        feature_collection = json.load(handle)

    lines = []
    for feature in feature_collection.get('features', []):
        geometry = feature.get('geometry')
        lines.extend(_iter_line_coordinates(geometry))

    if len(lines) == 0:
        return None, None

    temp = jigsawpy.jigsaw_msh_t()

    raw_coords = np.vstack([coords[:, :2] for coords in lines])

    # Merge vertices that are closer than snap_tolerance_km.  The tolerance
    # is expressed as a chord length in radians; for small angles this equals
    # the arc length, so snap_tolerance_km / earth_radius_km is accurate
    # enough for sub-degree separations.
    tol_rad = snap_tolerance_km / earth_radius_km
    raw_rad = np.radians(raw_coords)
    tree = cKDTree(raw_rad)
    pairs = tree.query_pairs(tol_rad)

    # Union-Find: assign every vertex to a canonical root.
    parent = np.arange(len(raw_rad))
    for i, j in pairs:
        ri, rj = _union_find(parent, i), _union_find(parent, j)
        if ri != rj:
            parent[rj] = ri

    roots = np.array([_union_find(parent, k) for k in range(len(raw_rad))])

    # Build unique cluster list and map each raw vertex to its cluster index.
    unique_roots, inverse = np.unique(roots, return_inverse=True)

    # Compute centroid for each cluster in radians.
    unique_rad = np.zeros((len(unique_roots), 2))
    counts = np.zeros(len(unique_roots))
    np.add.at(unique_rad, inverse, raw_rad)
    np.add.at(counts, inverse, 1)
    unique_rad /= counts[:, None]
    unique_rad, inverse = _merge_close_centroids(unique_rad, inverse, tol_rad)

    edge_starts = []
    edge_ends = []
    edge_tags = []
    raw_point_start = 0
    for line_index, coords in enumerate(lines, start=1):
        n = coords.shape[0]
        local = inverse[raw_point_start : raw_point_start + n]
        keep = local[:-1] != local[1:]
        edge_starts.append(local[:-1][keep].astype(np.int32))
        edge_ends.append(local[1:][keep].astype(np.int32))
        edge_tags.append(np.full(int(keep.sum()), line_index, dtype=np.int32))
        raw_point_start += n

    edge_starts = np.concatenate(edge_starts)
    edge_ends = np.concatenate(edge_ends)
    edge_tags = np.concatenate(edge_tags)

    # Remove duplicate edges (same cluster pair regardless of direction).
    edge_pairs = np.column_stack(
        [
            np.minimum(edge_starts, edge_ends),
            np.maximum(edge_starts, edge_ends),
        ]
    )
    _, unique_edge_indices = np.unique(edge_pairs, axis=0, return_index=True)
    edge_starts = edge_starts[unique_edge_indices]
    edge_ends = edge_ends[unique_edge_indices]
    edge_tags = edge_tags[unique_edge_indices]

    if edge_starts.size == 0:
        return None, None

    vert2: Any = np.zeros(len(unique_rad), dtype=temp.VERT2_t)
    edge2: Any = np.zeros(edge_starts.size, dtype=temp.EDGE2_t)

    vert2['coord'] = unique_rad
    edge2['index'][:, 0] = edge_starts
    edge2['index'][:, 1] = edge_ends
    edge2['IDtag'] = edge_tags

    return vert2, edge2


def _iter_line_coordinates(geometry):
    """
    Yield line coordinates from GeoJSON line-like geometries.
    """
    if geometry is None:
        return

    geometry_type = geometry.get('type')
    if geometry_type == 'LineString':
        coords = np.asarray(geometry['coordinates'], dtype=np.float64)
        if coords.shape[0] >= 2:
            yield coords
    elif geometry_type == 'MultiLineString':
        for coordinates in geometry['coordinates']:
            coords = np.asarray(coordinates, dtype=np.float64)
            if coords.shape[0] >= 2:
                yield coords
    elif geometry_type == 'GeometryCollection':
        for sub_geometry in geometry.get('geometries', []):
            yield from _iter_line_coordinates(sub_geometry)
