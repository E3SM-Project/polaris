import numpy as np
import pytest

from polaris.mesh.spherical.unified.effective_ocean import (
    block_average,
    build_effective_ocean_mask,
    flood_fill_from_seeds,
    hysteresis_grow,
    variable_box_average,
    widen_passages,
)

# a coarse global grid (4-degree resolution) for fast tests
RESOLUTION = 4.0
LAT = np.arange(-88.0, 89.0, RESOLUTION)
LON = np.arange(-180.0, 180.0, RESOLUTION)


def _grid_indices(lon0, lat0):
    return (
        int(np.argmin(np.abs(LAT - lat0))),
        int(np.argmin(np.abs(LON - lon0))),
    )


def _lagoon_candidate(barrier_fraction):
    """
    A mid-latitude ocean basin in the western half of the domain, a
    coastal lagoon just east of the coastline separated by a one-cell
    barrier column whose candidate fraction is ``barrier_fraction``,
    and dry land everywhere else (including poleward of 40 degrees, so
    nothing can connect around the poles where the longitude window
    widens).
    """
    fraction = np.zeros((LAT.size, LON.size))
    coast_col = LON.size // 2
    mid_lat = np.abs(LAT) < 40.0
    fraction[mid_lat, :coast_col] = 1.0
    # barrier column
    fraction[mid_lat, coast_col] = barrier_fraction
    # lagoon column (below sea level)
    fraction[mid_lat, coast_col + 1] = 1.0
    return fraction, coast_col


def test_block_average():
    field = np.arange(16.0).reshape(4, 4)
    averaged = block_average(field, 2)
    assert averaged.shape == (2, 2)
    np.testing.assert_allclose(averaged[0, 0], np.mean([0, 1, 4, 5]))

    with pytest.raises(ValueError, match='not divisible'):
        block_average(np.zeros((3, 4)), 2)


def test_variable_box_average_dilutes_barrier():
    # with a coarse (mesh-scale) averaging width, a thin barrier is
    # diluted above 0.5; with a fine width, it is preserved
    fraction, coast_col = _lagoon_candidate(barrier_fraction=0.0)

    coarse_width = np.full(fraction.shape, 2000.0)
    averaged = variable_box_average(
        frac=fraction, lat=LAT, resolution=RESOLUTION, width_km=coarse_width
    )
    row = LAT.size // 2
    assert averaged[row, coast_col] >= 0.5

    fine_width = np.full(fraction.shape, 100.0)
    averaged = variable_box_average(
        frac=fraction, lat=LAT, resolution=RESOLUTION, width_km=fine_width
    )
    assert averaged[row, coast_col] < 0.5


def test_flood_fill_from_seeds():
    mask = np.zeros((LAT.size, LON.size), dtype=bool)
    # two separate regions
    mask[10:15, 5:10] = True
    mask[20:25, 30:35] = True
    seed = (float(LON[7]), float(LAT[12]))
    filled = flood_fill_from_seeds(
        mask=mask, lat=LAT, lon=LON, seed_points=[seed]
    )
    assert filled[12, 7]
    assert not filled[22, 32]
    assert filled.sum() == mask[10:15, 5:10].sum()


def test_flood_fill_wraps_in_longitude():
    mask = np.zeros((LAT.size, LON.size), dtype=bool)
    # a band crossing the antimeridian
    mask[10, :5] = True
    mask[10, -5:] = True
    seed = (float(LON[-2]), float(LAT[10]))
    filled = flood_fill_from_seeds(
        mask=mask, lat=LAT, lon=LON, seed_points=[seed]
    )
    assert filled[10, 2]


def test_hysteresis_grow():
    filled = np.zeros((LAT.size, LON.size), dtype=bool)
    filled[10:15, 5:10] = True
    fraction = np.zeros(filled.shape)
    # a fringe connected to the filled region
    fraction[10:15, 10:12] = 0.4
    # an isolated inland depression with the same fraction
    fraction[30:32, 40:42] = 0.4
    grown = hysteresis_grow(filled=filled, frac=fraction, grow_threshold=0.35)
    assert grown[12, 10]
    assert not grown[30, 40]
    # original mask preserved
    assert grown[12, 7]


def test_widen_passages_scales_with_background():
    passages = np.zeros((LAT.size, LON.size), dtype=bool)
    row, col = _grid_indices(0.0, 0.0)
    passages[row, col] = True

    narrow = widen_passages(
        passages=passages,
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        width_km=np.full(passages.shape, 100.0),
        factor=1.5,
    )
    wide = widen_passages(
        passages=passages,
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        width_km=np.full(passages.shape, 2000.0),
        factor=1.5,
    )
    assert narrow.sum() >= 1
    assert wide.sum() > narrow.sum()


def test_widen_passages_high_lat_factor():
    passages = np.zeros((LAT.size, LON.size), dtype=bool)
    row_low, col = _grid_indices(0.0, 0.0)
    row_high, _ = _grid_indices(0.0, 60.0)
    passages[row_low, col] = True
    passages[row_high, col] = True

    widened = widen_passages(
        passages=passages,
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        width_km=np.full(passages.shape, 800.0),
        factor=1.0,
        high_lat_factor=3.0,
        latitude_threshold=43.0,
    )
    # meridional extent of the swath around each passage cell
    low_extent = int(np.sum(widened[:, col] & (np.abs(LAT) < 30.0)))
    high_extent = int(np.sum(widened[:, col] & (np.abs(LAT - 60.0) < 25.0)))
    assert high_extent > low_extent


def test_build_effective_ocean_mask_includes_lagoon():
    # the lagoon is separated by a dry barrier: at mesh scale the
    # barrier is diluted, so the emulated ocean must include the lagoon
    # even though the shared (fine-scale) coastline calls it land
    fraction, coast_col = _lagoon_candidate(barrier_fraction=0.0)
    shared = fraction >= 0.5
    shared[:, coast_col:] = False  # fine-scale mask: lagoon is land

    seed = (float(LON[2]), 0.0)
    fields = build_effective_ocean_mask(
        candidate_fraction=fraction,
        shared_ocean_mask=shared,
        ocean_background=np.full(fraction.shape, 2000.0),
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        seed_points=[seed],
    )
    row = LAT.size // 2
    assert fields['effective_ocean_mask'][row, coast_col + 1]

    # with a fine background, the barrier is resolved and the lagoon
    # stays land (it is disconnected from the seed)
    fields = build_effective_ocean_mask(
        candidate_fraction=fraction,
        shared_ocean_mask=shared,
        ocean_background=np.full(fraction.shape, 100.0),
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        seed_points=[seed],
        grow_threshold=None,
    )
    assert not fields['effective_ocean_mask'][row, coast_col + 1]


def test_build_effective_ocean_mask_respects_blockages():
    fraction = np.ones((LAT.size, LON.size))
    shared = np.zeros(fraction.shape, dtype=bool)
    blockages = np.zeros(fraction.shape, dtype=bool)
    # a meridional blockage wall splitting the domain
    wall_col = LON.size // 2
    blockages[:, wall_col] = True

    seed = (float(LON[2]), 0.0)
    fields = build_effective_ocean_mask(
        candidate_fraction=fraction,
        shared_ocean_mask=shared,
        ocean_background=np.full(fraction.shape, 100.0),
        lat=LAT,
        lon=LON,
        resolution=RESOLUTION,
        land_blockages=blockages,
        seed_points=[seed],
        grow_threshold=None,
    )
    emulated = fields['emulated_ocean_mask']
    row = LAT.size // 2
    assert not emulated[row, wall_col]
    assert emulated[row, 2]
