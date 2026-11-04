import logging

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.cull.dc_edge_diagnostics import (
    check_ocean_dc_edge,
    check_ocean_dv_edge,
)

LOGGER = logging.getLogger(__name__)

# the side of a regular hexagon as a fraction of its cell-center spacing
HEXAGON_SIDE = 1.0 / np.sqrt(3.0)


def test_check_ocean_dc_edge_passes(tmp_path):
    ds_base_mesh = _base_mesh(dc_edge_km=[30.0, 29.0, 31.0, 28.0])
    ds_sizing = _sizing(background_km=30.0)
    # all cells kept
    ocean_cull_mask = np.zeros(4, dtype=int)

    check_ocean_dc_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_cull_mask=ocean_cull_mask,
        ds_sizing=ds_sizing,
        min_ratio=0.65,
        max_ratio=1.5,
        min_abs_ratio=0.0,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        assert int(ds.oceanEdgeMask.sum()) == 3
        assert int(ds.dcEdgeTooSmallMask.sum()) == 0
        assert int(ds.dcEdgeTooLargeMask.sum()) == 0


def test_check_ocean_dc_edge_too_small(tmp_path):
    # one edge is much finer than the 30 km background
    ds_base_mesh = _base_mesh(dc_edge_km=[30.0, 10.0, 31.0, 28.0])
    ds_sizing = _sizing(background_km=30.0)
    ocean_cull_mask = np.zeros(4, dtype=int)

    with pytest.raises(ValueError, match='below min_dc_edge_ratio'):
        check_ocean_dc_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_cull_mask=ocean_cull_mask,
            ds_sizing=ds_sizing,
            min_ratio=0.65,
            max_ratio=1.5,
            min_abs_ratio=0.0,
            logger=LOGGER,
            out_filename=str(tmp_path / 'diags.nc'),
        )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        assert int(ds.dcEdgeTooSmallMask.sum()) == 1
        assert int(ds.dcEdgeTooLargeMask.sum()) == 0


def test_check_ocean_dc_edge_too_large(tmp_path):
    ds_base_mesh = _base_mesh(dc_edge_km=[30.0, 50.0, 31.0, 28.0])
    ds_sizing = _sizing(background_km=30.0)
    ocean_cull_mask = np.zeros(4, dtype=int)

    with pytest.raises(ValueError, match='above max_dc_edge_ratio'):
        check_ocean_dc_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_cull_mask=ocean_cull_mask,
            ds_sizing=ds_sizing,
            min_ratio=0.65,
            max_ratio=1.5,
            min_abs_ratio=0.0,
            logger=LOGGER,
            out_filename=str(tmp_path / 'diags.nc'),
        )


def test_check_ocean_dc_edge_ignores_culled_and_boundary(tmp_path):
    # the fine edge is adjacent to a culled cell, so it is not an
    # ocean-interior edge and must not trigger a failure; the edge with
    # a missing neighbor (cellsOnEdge == 0) must also be skipped
    ds_base_mesh = _base_mesh(dc_edge_km=[30.0, 10.0, 31.0, 9.0])
    ds_sizing = _sizing(background_km=30.0)
    # cull the cell adjacent to the 10 km edge
    ocean_cull_mask = np.array([0, 0, 1, 0])

    check_ocean_dc_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_cull_mask=ocean_cull_mask,
        ds_sizing=ds_sizing,
        min_ratio=0.65,
        max_ratio=1.5,
        min_abs_ratio=0.0,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        # only the first edge is ocean-interior
        np.testing.assert_array_equal(ds.oceanEdgeMask.values, [1, 0, 0, 0])


def test_check_ocean_dc_edge_local_background(tmp_path):
    # a 10 km edge is fine where the local background is 12 km but a
    # failure where it is 30 km
    ds_sizing = _sizing(background_km=None)
    ds_base_mesh = _base_mesh(
        dc_edge_km=[10.0, 10.0, 30.0, 30.0],
        lat_edge=[-70.0, -70.0, 40.0, 40.0],
    )
    ocean_cull_mask = np.zeros(4, dtype=int)

    check_ocean_dc_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_cull_mask=ocean_cull_mask,
        ds_sizing=ds_sizing,
        min_ratio=0.65,
        max_ratio=1.5,
        min_abs_ratio=0.0,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )


def test_check_ocean_dc_edge_abs_guard_fails_on_a_short_edge(tmp_path):
    """
    The CFL guard measures the shortest edge against the finest ocean
    background anywhere, since that is what sets the time step.
    """
    ds_sizing = _sizing(background_km=None)
    # 6 km edge where the fine background is 12 km: half the finest
    # background anywhere, so the time step has to shrink
    ds_base_mesh = _base_mesh(
        dc_edge_km=[6.0, 11.0, 28.0, 28.0],
        lat_edge=[-70.0, -70.0, 40.0, 40.0],
    )
    ocean_cull_mask = np.zeros(4, dtype=int)

    with pytest.raises(ValueError, match='shortest edge'):
        check_ocean_dc_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_cull_mask=ocean_cull_mask,
            ds_sizing=ds_sizing,
            min_ratio=0.0,
            max_ratio=10.0,
            min_abs_ratio=0.70,
            logger=LOGGER,
            out_filename=str(tmp_path / 'diags.nc'),
        )


def test_check_ocean_dc_edge_abs_guard_ignores_coarse_region_blemish(
    tmp_path,
):
    """
    An edge that is short only relative to a *coarse* local background is
    still longer than the mesh's finest intended resolution, so it cannot
    constrain the global time step.  This is the u-oi6to18-lr6to10 case:
    an 8 km edge in a 15.9 km background on a mesh whose finest ocean
    background is 6 km.
    """
    ds_sizing = _sizing(background_km=None)
    # the 15 km edge sits in the 30 km background: local ratio 0.5, but it
    # is comfortably longer than the 12 km finest background
    ds_base_mesh = _base_mesh(
        dc_edge_km=[11.0, 11.0, 15.0, 30.0],
        lat_edge=[-70.0, -70.0, 40.0, 40.0],
    )
    ocean_cull_mask = np.zeros(4, dtype=int)

    check_ocean_dc_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_cull_mask=ocean_cull_mask,
        ds_sizing=ds_sizing,
        min_ratio=0.0,
        max_ratio=10.0,
        min_abs_ratio=0.70,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        assert ds.attrs['min_dc_edge_abs_ratio'] == 0.70


def test_check_ocean_dv_edge_passes(tmp_path):
    """
    A regular hexagonal mesh has a dvEdge ratio of 1, and every edge of a
    kept cell is checked, including the one with a missing neighbor.
    """
    ds_base_mesh = _base_mesh(dc_edge_km=[30.0, 30.0, 30.0, 30.0])
    ds_sizing = _sizing(background_km=30.0)
    ocean_no_cavities_cull_mask = np.zeros(4, dtype=int)

    check_ocean_dv_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_no_cavities_cull_mask=ocean_no_cavities_cull_mask,
        ds_sizing=ds_sizing,
        min_abs_ratio=0.35,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        assert int(ds.oceanDomainEdgeMask.sum()) == 4
        np.testing.assert_allclose(ds.dvEdgeRatio.values, 1.0)
        assert ds.attrs['min_dv_edge_abs_ratio'] == 0.35


def test_check_ocean_dv_edge_fails_on_a_short_edge(tmp_path):
    """
    A cell side a quarter as long as a regular hexagon's limits the
    sea-ice time step even where dcEdge is unremarkable.
    """
    side = 30.0 * HEXAGON_SIDE
    ds_base_mesh = _base_mesh(
        dc_edge_km=[30.0, 30.0, 30.0, 30.0],
        dv_edge_km=[side, 0.25 * side, side, side],
    )
    ds_sizing = _sizing(background_km=30.0)
    ocean_no_cavities_cull_mask = np.zeros(4, dtype=int)

    with pytest.raises(ValueError, match='sea-ice time step'):
        check_ocean_dv_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_no_cavities_cull_mask=ocean_no_cavities_cull_mask,
            ds_sizing=ds_sizing,
            min_abs_ratio=0.35,
            logger=LOGGER,
            out_filename=str(tmp_path / 'diags.nc'),
        )


def test_check_ocean_dv_edge_includes_coastline_edges(tmp_path):
    """
    With cell 4 culled, edge 3 lies on the coastline between kept cell 3
    and culled cell 4.  Sea-ice advection uses it, so it is checked.
    """
    side = 30.0 * HEXAGON_SIDE
    ds_base_mesh = _base_mesh(
        dc_edge_km=[30.0, 30.0, 30.0, 30.0],
        dv_edge_km=[side, side, 0.25 * side, side],
    )
    ds_sizing = _sizing(background_km=30.0)
    ocean_no_cavities_cull_mask = np.array([0, 0, 0, 1])

    with pytest.raises(ValueError, match='sea-ice time step'):
        check_ocean_dv_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_no_cavities_cull_mask=ocean_no_cavities_cull_mask,
            ds_sizing=ds_sizing,
            min_abs_ratio=0.35,
            logger=LOGGER,
            out_filename=str(tmp_path / 'diags.nc'),
        )


def test_check_ocean_dv_edge_ignores_culled_edges(tmp_path):
    """
    With cell 4 culled, edge 4 (cell 4 and a missing neighbor) belongs to
    no kept cell, so a short side there does not matter.
    """
    side = 30.0 * HEXAGON_SIDE
    ds_base_mesh = _base_mesh(
        dc_edge_km=[30.0, 30.0, 30.0, 30.0],
        dv_edge_km=[side, side, side, 0.25 * side],
    )
    ds_sizing = _sizing(background_km=30.0)
    ocean_no_cavities_cull_mask = np.array([0, 0, 0, 1])

    check_ocean_dv_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_no_cavities_cull_mask=ocean_no_cavities_cull_mask,
        ds_sizing=ds_sizing,
        min_abs_ratio=0.35,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        assert int(ds.oceanDomainEdgeMask.sum()) == 3
        assert np.isnan(ds.dvEdgeRatio.values[3])


def test_check_ocean_dv_edge_uses_finest_background(tmp_path):
    """
    As for dcEdge, a side that is short only relative to a coarse local
    background is still longer than the regular-hexagon side at the finest
    background, so it cannot constrain the time step.  The diagnostics
    file still records the local ratio.
    """
    ds_sizing = _sizing(background_km=None)
    # half a 30 km hexagon side is 1.25 times a 12 km hexagon side
    ds_base_mesh = _base_mesh(
        dc_edge_km=[12.0, 12.0, 30.0, 30.0],
        dv_edge_km=[
            12.0 * HEXAGON_SIDE,
            12.0 * HEXAGON_SIDE,
            0.5 * 30.0 * HEXAGON_SIDE,
            30.0 * HEXAGON_SIDE,
        ],
        lat_edge=[-70.0, -70.0, 40.0, 40.0],
    )
    ocean_no_cavities_cull_mask = np.zeros(4, dtype=int)

    check_ocean_dv_edge(
        ds_base_mesh=ds_base_mesh,
        ocean_no_cavities_cull_mask=ocean_no_cavities_cull_mask,
        ds_sizing=ds_sizing,
        min_abs_ratio=0.7,
        logger=LOGGER,
        out_filename=str(tmp_path / 'diags.nc'),
    )

    with xr.open_dataset(tmp_path / 'diags.nc') as ds:
        np.testing.assert_allclose(ds.dvEdgeRatio.values[2], 0.5)


def _base_mesh(dc_edge_km, lat_edge=None, dv_edge_km=None):
    """
    A tiny synthetic mesh: 4 cells in a ring, 4 edges.  Edge i connects
    cells i and i+1 (1-based, periodic), except the last edge, which has
    a missing second neighbor (0) to exercise boundary handling.  By
    default, each ``dvEdge`` is the side of a regular hexagon with the
    edge's ``dcEdge``.
    """
    n_edges = len(dc_edge_km)
    cells_on_edge = np.array([[1, 2], [2, 3], [3, 4], [4, 0]], dtype=np.int32)
    if lat_edge is None:
        lat_edge = np.zeros(n_edges)
    if dv_edge_km is None:
        dv_edge_km = HEXAGON_SIDE * np.asarray(dc_edge_km, dtype=float)
    lon_edge = np.linspace(10.0, 40.0, n_edges)
    return xr.Dataset(
        data_vars=dict(
            dcEdge=('nEdges', 1e3 * np.asarray(dc_edge_km, dtype=float)),
            dvEdge=('nEdges', 1e3 * np.asarray(dv_edge_km, dtype=float)),
            latEdge=('nEdges', np.radians(lat_edge)),
            lonEdge=('nEdges', np.radians(lon_edge)),
            cellsOnEdge=(('nEdges', 'TWO'), cells_on_edge),
        )
    )


def _sizing(background_km):
    """
    A coarse global lat/lon sizing dataset.  If ``background_km`` is
    None, the background is 12 km south of 45 S and 30 km elsewhere
    (mimicking a Southern Ocean regional refinement).
    """
    lat = np.linspace(-89.0, 89.0, 90)
    lon = np.linspace(-179.0, 179.0, 180)
    if background_km is None:
        background = np.where(lat < -45.0, 12.0, 30.0)[:, np.newaxis]
        background = background * np.ones((lat.size, lon.size))
    else:
        background = np.full((lat.size, lon.size), background_km)
    return xr.Dataset(
        coords=dict(lat=('lat', lat), lon=('lon', lon)),
        data_vars=dict(
            ocean_background_cell_width=(('lat', 'lon'), background)
        ),
    )
