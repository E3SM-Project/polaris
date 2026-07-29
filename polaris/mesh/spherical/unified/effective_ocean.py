"""
Build a per-mesh "effective ocean mask" on a lat/lon sizing grid that
anticipates what the MPAS cull will keep as ocean/sea-ice.

The MPAS cull decides ocean ownership from the conservative
below-sea-level area fraction (``ocean_frac``) on mesh-scale cells plus
a flood fill, so its coastline topology differs from the fine-scale
lat/lon coastline products: thin land barriers that disconnect coastal
lagoons at fine resolution are diluted away at mesh scale.  The
functions here emulate the cull on the sizing grid — mesh-scale
averaging of the candidate-ocean fraction, critical-transect handling
with resolution-proportional passage widening, a seeded flood fill and
hysteresis growth — so the sizing field can prescribe the full ocean
background cell width everywhere the cull is likely to keep.

See the ``unified_mesh_cull_leak`` design doc for the motivation,
algorithm details and validation.
"""

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from polaris.constants import get_constant

EARTH_RADIUS = get_constant('mean_radius')
KM_PER_DEG = np.pi / 180.0 * EARTH_RADIUS / 1e3


def build_effective_ocean_mask(
    candidate_fraction,
    shared_ocean_mask,
    ocean_background,
    lat,
    lon,
    resolution,
    land_blockages=None,
    passages=None,
    seed_points=None,
    grow_threshold=0.35,
    passage_widen_factor=1.5,
    passage_widen_factor_high_lat=3.0,
    passage_widen_latitude_threshold=43.0,
):
    """
    Build the effective ocean mask by emulating the MPAS cull.

    Parameters
    ----------
    candidate_fraction : numpy.ndarray
        The candidate-ocean area fraction on the sizing grid (the
        conservative average of the source ocean mask, the same
        quantity that becomes ``ocean_frac`` on the MPAS mesh), with
        dimensions ``(lat, lon)``

    shared_ocean_mask : numpy.ndarray
        The flood-filled ocean mask from the shared coastline products
        on the same grid

    ocean_background : numpy.ndarray
        The ocean background cell width in km on the same grid

    lat : numpy.ndarray
        The latitude coordinate in degrees

    lon : numpy.ndarray
        The longitude coordinate in degrees

    resolution : float
        The grid resolution in degrees

    land_blockages : numpy.ndarray, optional
        A boolean mask of rasterized critical land blockages (removed
        from the emulated ocean)

    passages : numpy.ndarray, optional
        A boolean mask of rasterized critical ocean passages (widened
        and added to the emulated ocean)

    seed_points : list of tuple, optional
        ``(lon, lat)`` seed points in degrees for the flood fill; if
        ``None``, no flood fill is performed and all mesh-scale ocean
        is retained

    grow_threshold : float, optional
        The hysteresis lower bound on the candidate fraction (< 0.5);
        connected regions above this threshold that touch the strict
        flood-filled ocean are added, covering cells whose fate at the
        strict 0.5 threshold depends on the exact MPAS cell tiling

    passage_widen_factor : float, optional
        The passage swath width in units of the local ocean background
        cell width

    passage_widen_factor_high_lat : float, optional
        The passage swath width factor poleward of
        ``passage_widen_latitude_threshold`` (mimicking
        ``widen_transect_edge_masks`` in the MPAS cull)

    passage_widen_latitude_threshold : float, optional
        The latitude in degrees poleward of which
        ``passage_widen_factor_high_lat`` applies

    Returns
    -------
    fields : dict of str to numpy.ndarray
        ``'effective_ocean_mask'``: the union of the shared and
        emulated ocean masks; ``'emulated_ocean_mask'``: the
        flood-filled, hysteresis-grown mesh-scale ocean mask;
        ``'mesh_scale_fraction'``: the mesh-scale candidate fraction;
        ``'passages_widened'``: the widened passage mask
    """
    mesh_scale_fraction = variable_box_average(
        frac=candidate_fraction,
        lat=lat,
        resolution=resolution,
        width_km=ocean_background,
    )
    emulated = mesh_scale_fraction >= 0.5

    if passages is not None:
        passages_widened = widen_passages(
            passages=passages,
            lat=lat,
            lon=lon,
            resolution=resolution,
            width_km=ocean_background,
            factor=passage_widen_factor,
            high_lat_factor=passage_widen_factor_high_lat,
            latitude_threshold=passage_widen_latitude_threshold,
        )
    else:
        passages_widened = np.zeros(emulated.shape, dtype=bool)

    if land_blockages is not None:
        emulated = np.logical_and(emulated, np.logical_not(land_blockages))
    emulated = np.logical_or(emulated, passages_widened)

    if seed_points is not None:
        emulated = flood_fill_from_seeds(
            mask=emulated, lat=lat, lon=lon, seed_points=seed_points
        )

    if grow_threshold is not None and grow_threshold < 0.5:
        grow_fraction = mesh_scale_fraction
        if land_blockages is not None:
            grow_fraction = np.where(
                np.logical_not(land_blockages), grow_fraction, 0.0
            )
        grow_fraction = np.where(passages_widened, 1.0, grow_fraction)
        emulated = hysteresis_grow(
            filled=emulated,
            frac=grow_fraction,
            grow_threshold=grow_threshold,
        )

    effective = np.logical_or(shared_ocean_mask, emulated)

    return dict(
        effective_ocean_mask=effective,
        emulated_ocean_mask=emulated,
        mesh_scale_fraction=mesh_scale_fraction,
        passages_widened=passages_widened,
    )


def block_average(field, factor):
    """
    Block-average a 2D field by an integer factor in both dimensions.

    Parameters
    ----------
    field : numpy.ndarray
        The field to average, with dimensions ``(lat, lon)`` divisible
        by ``factor``

    factor : int
        The block size

    Returns
    -------
    averaged : numpy.ndarray
        The block-averaged field
    """
    if factor == 1:
        return field
    nlat, nlon = field.shape
    if nlat % factor != 0 or nlon % factor != 0:
        raise ValueError(
            f'Field shape {field.shape} is not divisible by {factor}.'
        )
    return field.reshape(nlat // factor, factor, nlon // factor, factor).mean(
        axis=(1, 3)
    )


def variable_box_average(frac, lat, resolution, width_km, max_window=720):
    """
    Box-average a fraction over a local window of ``width_km``,
    emulating the conservative area fraction on mesh-scale cells.

    The width field is quantized into geometric bins; each bin gets a
    separable box filter (nearest at the latitude boundaries, periodic
    in longitude) whose longitude window grows as 1/cos(latitude).

    Parameters
    ----------
    frac : numpy.ndarray
        The fraction to average, with dimensions ``(lat, lon)``

    lat : numpy.ndarray
        The latitude coordinate in degrees

    resolution : float
        The grid resolution in degrees

    width_km : numpy.ndarray
        The local averaging width in km on the same grid

    max_window : int, optional
        The maximum longitude window in grid cells (limits cost near
        the poles)

    Returns
    -------
    averaged : numpy.ndarray
        The locally averaged fraction
    """
    dlat_km = resolution * KM_PER_DEG
    width_km = np.maximum(width_km, dlat_km)
    log_width = np.log(width_km)
    log_range = log_width.max() - log_width.min()
    nbins = max(1, int(np.ceil(log_range / np.log(1.3))))
    edges = np.linspace(log_width.min(), log_width.max(), nbins + 1)
    centers = np.exp(0.5 * (edges[:-1] + edges[1:]))
    bin_index = np.clip(np.digitize(log_width, edges) - 1, 0, nbins - 1)

    cos_lat = np.maximum(np.cos(np.radians(lat)), 1e-3)
    out = np.empty_like(frac)
    for bin, width in enumerate(centers):
        rows = np.nonzero(np.any(bin_index == bin, axis=1))[0]
        if rows.size == 0:
            continue
        lat_window = max(1, int(round(width / dlat_km)))
        filtered = ndimage.uniform_filter1d(
            frac, size=lat_window, axis=0, mode='nearest'
        )
        for row in rows:
            lon_window = max(1, int(round(width / (dlat_km * cos_lat[row]))))
            lon_window = min(lon_window, max_window)
            values = ndimage.uniform_filter1d(
                filtered[row], size=lon_window, mode='wrap'
            )
            mask = bin_index[row] == bin
            out[row, mask] = values[mask]
    return out


def widen_passages(
    passages,
    lat,
    lon,
    resolution,
    width_km,
    factor,
    high_lat_factor=None,
    latitude_threshold=43.0,
):
    """
    Dilate rasterized passage lines to a swath proportional to the
    local ocean background cell width.

    Parameters
    ----------
    passages : numpy.ndarray
        A boolean mask of rasterized passage lines, with dimensions
        ``(lat, lon)``

    lat : numpy.ndarray
        The latitude coordinate in degrees

    lon : numpy.ndarray
        The longitude coordinate in degrees

    resolution : float
        The grid resolution in degrees

    width_km : numpy.ndarray
        The local ocean background cell width in km on the same grid

    factor : float
        The swath width in units of the local background cell width
        (the dilation radius is half the swath width)

    high_lat_factor : float, optional
        The swath width factor poleward of ``latitude_threshold``

    latitude_threshold : float, optional
        The latitude in degrees poleward of which ``high_lat_factor``
        applies

    Returns
    -------
    widened : numpy.ndarray
        The widened passage mask
    """
    if factor <= 0.0 or not passages.any():
        return passages.copy()

    rows, cols = np.nonzero(passages)
    tree = cKDTree(_lon_lat_to_xyz(lon[cols], lat[rows]))

    factor_2d = np.full((lat.size, lon.size), factor, dtype=float)
    if high_lat_factor is not None:
        factor_2d[np.abs(lat) > latitude_threshold, :] = high_lat_factor
    radius_km = 0.5 * factor_2d * width_km
    max_radius_km = float(np.max(radius_km))
    pad = int(np.ceil(max_radius_km / (resolution * KM_PER_DEG))) + 1

    # only query grid cells near the passages
    region = ndimage.binary_dilation(
        passages, structure=np.ones((3, 3), dtype=bool), iterations=pad
    )
    r_rows, r_cols = np.nonzero(region)
    chord, _ = tree.query(_lon_lat_to_xyz(lon[r_cols], lat[r_rows]))
    chord = np.clip(chord, 0.0, 2.0)
    distance_km = 2.0 * np.arcsin(0.5 * chord) * EARTH_RADIUS / 1e3
    keep = distance_km <= radius_km[r_rows, r_cols]
    widened = passages.copy()
    widened[r_rows[keep], r_cols[keep]] = True
    return widened


def flood_fill_from_seeds(mask, lat, lon, seed_points):
    """
    Keep the connected components of a mask that contain seed points.

    Connectivity is 4-connected with periodic wrap in longitude.

    Parameters
    ----------
    mask : numpy.ndarray
        A boolean mask with dimensions ``(lat, lon)``

    lat : numpy.ndarray
        The latitude coordinate in degrees

    lon : numpy.ndarray
        The longitude coordinate in degrees

    seed_points : list of tuple
        ``(lon, lat)`` seed points in degrees

    Returns
    -------
    filled : numpy.ndarray
        The mask restricted to components containing seed points
    """
    labels, count, find = _label_with_wrap(mask)
    if count == 0:
        return np.zeros_like(mask)

    seed_roots = set()
    for point_lon, point_lat in seed_points:
        row = int(np.argmin(np.abs(lat - point_lat)))
        delta = np.mod(lon - point_lon + 180.0, 360.0) - 180.0
        col = int(np.argmin(np.abs(delta)))
        if mask[row, col]:
            seed_roots.add(find(labels[row, col]))

    return _keep_components(labels, count, find, seed_roots, mask)


def hysteresis_grow(filled, frac, grow_threshold):
    """
    Grow a flood-filled ocean mask into connected regions whose
    fraction is at least ``grow_threshold``.

    Only components of the lower-threshold mask that touch the strict
    flood-filled ocean are added, so isolated inland regions are not
    promoted.

    Parameters
    ----------
    filled : numpy.ndarray
        The strict flood-filled ocean mask, with dimensions
        ``(lat, lon)``

    frac : numpy.ndarray
        The mesh-scale candidate fraction on the same grid

    grow_threshold : float
        The lower bound on the fraction for growth

    Returns
    -------
    grown : numpy.ndarray
        The grown mask
    """
    grow_mask = np.logical_or(filled, frac >= grow_threshold)
    labels, count, find = _label_with_wrap(grow_mask)
    if count == 0:
        return filled

    seed_labels = np.unique(labels[filled])
    seed_roots = {find(label) for label in seed_labels if label != 0}
    if not seed_roots:
        return filled

    return _keep_components(labels, count, find, seed_roots, grow_mask)


def _label_with_wrap(mask):
    """
    Label 4-connected components with longitude wrap via union-find.

    Returns the label array, the label count and a ``find`` function
    that resolves a label to its wrap-merged root.
    """
    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8)
    labels, count = ndimage.label(mask, structure=structure)
    parent = np.arange(count + 1, dtype=np.int64)

    def find(label):
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    wrap_rows = np.nonzero(mask[:, 0] & mask[:, -1])[0]
    for row in wrap_rows:
        left = find(labels[row, 0])
        right = find(labels[row, -1])
        if left != right:
            parent[right] = left

    return labels, count, find


def _keep_components(labels, count, find, seed_roots, mask):
    """
    Build a mask of the components whose roots are in ``seed_roots``.
    """
    if not seed_roots:
        return np.zeros_like(mask)
    keep = np.zeros(count + 1, dtype=bool)
    for label in range(1, count + 1):
        keep[label] = find(label) in seed_roots
    return keep[labels]


def _lon_lat_to_xyz(lon, lat):
    """
    Convert lon/lat in degrees to Cartesian points on the unit sphere.
    """
    lon_rad = np.radians(lon)
    lat_rad = np.radians(lat)
    cos_lat = np.cos(lat_rad)
    return np.column_stack(
        [
            cos_lat * np.cos(lon_rad),
            cos_lat * np.sin(lon_rad),
            np.sin(lat_rad),
        ]
    )
