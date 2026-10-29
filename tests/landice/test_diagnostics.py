import logging

import numpy as np
import pytest
import xarray as xr

from polaris.landice.diagnostics import (
    compute_volume_and_area,
    grounding_line_on_row,
    grounding_line_points,
    thickness_above_flotation,
)
from polaris.landice.mismip_plus.mesh import make_mismip_plus_mesh

ICE_DENSITY = 910.0
OCEAN_DENSITY = 1025.0
BED = -500.0


@pytest.fixture(scope='module')
def ds_mesh():
    logger = logging.getLogger(__name__)
    return make_mismip_plus_mesh(resolution=8.0, logger=logger)


def _linear_ice(ds_mesh, x_gl):
    """
    Ice whose thickness above flotation is zero at x_gl and changes
    linearly with x
    """
    x = ds_mesh.xCell
    flotation = OCEAN_DENSITY / ICE_DENSITY * -BED
    thickness = flotation + 1.0e-3 * (x_gl - x)
    thickness = thickness.clip(min=0.0)
    bed = xr.full_like(x, BED)
    return thickness, bed


def test_thickness_above_flotation():
    thickness = xr.DataArray([100.0, 600.0, 0.0])
    bed = xr.DataArray([-500.0, -500.0, 200.0])
    haf = thickness_above_flotation(thickness, bed, 900.0, 1000.0)
    flotation = 5000.0 / 9.0
    np.testing.assert_allclose(
        haf, [100.0 - flotation, 600.0 - flotation, 0.0]
    )


def test_compute_volume_and_area(ds_mesh):
    thickness, bed = _linear_ice(ds_mesh, x_gl=300.0e3)
    ds = compute_volume_and_area(
        thickness, bed, ds_mesh.areaCell, ICE_DENSITY, OCEAN_DENSITY
    )
    area = ds_mesh.areaCell.values
    haf = thickness.values + OCEAN_DENSITY / ICE_DENSITY * BED
    grounded = haf > 0.0
    np.testing.assert_allclose(ds.iceVolume, (thickness.values * area).sum())
    np.testing.assert_allclose(
        ds.iceVAF, (haf[grounded] * area[grounded]).sum()
    )
    np.testing.assert_allclose(ds.groundedArea, area[grounded].sum())


def test_grounding_line_points(ds_mesh):
    x_gl = 300.0e3
    thickness, bed = _linear_ice(ds_mesh, x_gl=x_gl)
    haf = thickness_above_flotation(thickness, bed, ICE_DENSITY, OCEAN_DENSITY)
    x, y = grounding_line_points(haf, ds_mesh)

    # every edge that straddles x_gl has a point on it, at x_gl
    x_cell = ds_mesh.xCell.values
    cells = ds_mesh.cellsOnEdge.values - 1
    cells = cells[np.all(cells >= 0, axis=1)]
    straddles = (x_cell[cells[:, 0]] - x_gl) * (x_cell[cells[:, 1]] - x_gl) < 0
    assert x.size == straddles.sum() > 0
    np.testing.assert_allclose(x, x_gl)
    # the points span the domain across the flow
    assert y.min() < 8.0e3
    assert y.max() > 72.0e3

    with pytest.raises(ValueError):
        grounding_line_points(haf.expand_dims('Time'), ds_mesh)


def test_grounding_line_on_row(ds_mesh):
    x_gl = 300.0e3
    thickness, bed = _linear_ice(ds_mesh, x_gl=x_gl)
    haf = thickness_above_flotation(thickness, bed, ICE_DENSITY, OCEAN_DENSITY)
    y_row = float(np.median(np.unique(ds_mesh.yCell.values)))

    x_row = grounding_line_on_row(haf, ds_mesh, y_row)
    np.testing.assert_allclose(x_row, x_gl)

    x_time = grounding_line_on_row(
        xr.concat([haf, haf], dim='Time'), ds_mesh, y_row
    )
    assert x_time.dims == ('Time',)
    np.testing.assert_allclose(x_time, x_gl)

    with pytest.raises(ValueError):
        grounding_line_on_row(haf, ds_mesh, y_row + 1.0e3)
