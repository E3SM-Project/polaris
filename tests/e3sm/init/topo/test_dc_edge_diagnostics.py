import logging

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.topo.cull.dc_edge_diagnostics import (
    check_ocean_dc_edge,
)

LOGGER = logging.getLogger(__name__)


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
    constrain the global time step.  This is the u.oi6to18.lr6to10 case:
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


def _base_mesh(dc_edge_km, lat_edge=None):
    """
    A tiny synthetic mesh: 4 cells in a ring, 4 edges.  Edge i connects
    cells i and i+1 (1-based, periodic), except the last edge, which has
    a missing second neighbor (0) to exercise boundary handling.
    """
    n_edges = len(dc_edge_km)
    cells_on_edge = np.array([[1, 2], [2, 3], [3, 4], [4, 0]], dtype=np.int32)
    if lat_edge is None:
        lat_edge = np.zeros(n_edges)
    lon_edge = np.linspace(10.0, 40.0, n_edges)
    return xr.Dataset(
        data_vars=dict(
            dcEdge=('nEdges', 1e3 * np.asarray(dc_edge_km, dtype=float)),
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
