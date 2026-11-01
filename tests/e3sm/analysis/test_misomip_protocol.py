import numpy as np
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.protocol import (
    PROTOCOL_X,
    PROTOCOL_Y,
    bin_column,
    write_protocol_scrip,
)


def test_a_column_is_averaged_over_bins_by_overlap():
    """Layers of 0 to -7 m (1) and -7 to -20 m (2) in 5 m bins: the second
    bin holds 2 m of the first layer and 3 m of the second; the fifth bin
    is below the column."""
    values = np.array([1.0, 2.0, np.nan])
    z_top = np.array([0.0, -7.0, -20.0])
    z_bottom = np.array([-7.0, -20.0, -20.0])
    z_edges = np.array([0.0, -5.0, -10.0, -15.0, -20.0, -25.0])

    binned = bin_column(values, z_top, z_bottom, z_edges)

    np.testing.assert_allclose(binned[:4], [1.0, 1.6, 2.0, 2.0])
    assert np.isnan(binned[4])


def test_the_protocol_grid_has_the_projection_s_coordinates(tmp_path):
    filename = str(tmp_path / 'protocol_scrip.nc')

    write_protocol_scrip(filename)

    ds = xr.open_dataset(filename)
    assert ds.sizes['grid_size'] == len(PROTOCOL_X) * len(PROTOCOL_Y)
    assert ds.sizes['grid_corners'] == 4
    assert list(ds.grid_dims.values) == [240, 40]
    # the box is near 75 S, as the projection puts its center there
    assert -78.0 < float(ds.grid_center_lat.min())
    assert float(ds.grid_center_lat.max()) < -72.0
