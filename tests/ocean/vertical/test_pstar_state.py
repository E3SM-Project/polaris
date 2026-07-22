import gsw
import numpy as np
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.vertical.pstar_state import (
    add_density_from_specvol,
    add_quiescent_normal_velocity,
    convert_tracers_to_mpas_ocean,
    layer_thickness_from_geom_interfaces,
)


def _make_geom_ds():
    """A 2-cell, 3-layer dataset where the second cell only has 2 valid
    layers."""
    geom_z_inter = np.array(
        [
            [[0.0, -10.0, -20.0, -30.0], [0.0, -10.0, -25.0, -25.0]],
        ]
    )
    cell_mask = np.array(
        [
            [True, True, True],
            [True, True, False],
        ]
    )
    return xr.Dataset(
        data_vars=dict(
            GeomZInterface=(
                ('Time', 'nCells', 'nVertLevelsP1'),
                geom_z_inter,
            ),
            cellMask=(('nCells', 'nVertLevels'), cell_mask),
        )
    )


def test_layer_thickness_from_geom_interfaces():
    ds = _make_geom_ds()
    ds = layer_thickness_from_geom_interfaces(ds)

    expected = np.array(
        [
            [[10.0, 10.0, 10.0], [10.0, 15.0, 0.0]],
        ]
    )
    assert_allclose(ds.restingThickness.values, expected)
    assert_allclose(ds.layerThickness.values, expected)
    assert ds.restingThickness.dims == ('Time', 'nCells', 'nVertLevels')
    assert ds.restingThickness.attrs['units'] == 'm'
    assert ds.layerThickness.attrs['long_name'] == 'layer thickness'


def test_add_quiescent_normal_velocity():
    ds = xr.Dataset(
        data_vars=dict(
            temperature=(
                ('Time', 'nCells', 'nVertLevels'),
                np.ones((1, 2, 3)),
            ),
        )
    )
    ds_mesh = xr.Dataset(
        data_vars=dict(xEdge=(('nEdges',), np.zeros(5))),
    )
    ds = add_quiescent_normal_velocity(ds, ds_mesh)

    assert ds.normalVelocity.dims == ('Time', 'nEdges', 'nVertLevels')
    assert ds.normalVelocity.shape == (1, 5, 3)
    assert_allclose(ds.normalVelocity.values, 0.0)
    assert ds.normalVelocity.attrs['units'] == 'm s-1'


def test_add_density_from_specvol():
    spec_vol = np.array([[[1.0e-3, 9.7e-4]]])
    ds = xr.Dataset(
        data_vars=dict(
            SpecVol=(('Time', 'nCells', 'nVertLevels'), spec_vol),
        )
    )
    ds = add_density_from_specvol(ds)

    assert_allclose(ds.Density.values, 1.0 / spec_vol)
    assert ds.Density.attrs['long_name'] == 'in-situ density'
    assert ds.Density.attrs['units'] == 'kg m-3'


def _make_tracer_ds():
    ct = np.array([[[10.0, 12.0], [20.0, np.nan]]])
    sa = np.array([[[35.0, 35.2], [34.8, np.nan]]])
    pressure = np.array([[[1.0e5, 2.0e6], [1.0e5, 2.0e6]]])
    return xr.Dataset(
        data_vars=dict(
            temperature=(('Time', 'nCells', 'nVertLevels'), ct),
            salinity=(('Time', 'nCells', 'nVertLevels'), sa),
            pressure=(('Time', 'nCells', 'nVertLevels'), pressure),
        )
    )


def test_convert_tracers_to_mpas_ocean_nominal_location():
    ds = _make_tracer_ds()
    ct = ds.temperature.values.copy()
    sa = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = 0.0
    lat = 0.0

    ds = convert_tracers_to_mpas_ocean(ds, lon=lon, lat=lat)

    valid = np.isfinite(ct)
    expected_pt = gsw.pt_from_CT(sa[valid], ct[valid])
    expected_sp = gsw.SP_from_SA(sa[valid], p_dbar[valid], lon, lat)

    assert_allclose(ds.temperature.values[valid], expected_pt)
    assert_allclose(ds.salinity.values[valid], expected_sp)
    # invalid (below-bottom) values stay NaN
    assert np.isnan(ds.temperature.values[~valid]).all()
    assert np.isnan(ds.salinity.values[~valid]).all()
    assert ds.temperature.attrs['long_name'] == 'potential temperature'
    assert ds.salinity.attrs['units'] == 'PSU'


def test_convert_tracers_to_mpas_ocean_per_cell_location():
    ds = _make_tracer_ds()
    sa = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = np.array([0.0, 180.0])
    lat = np.array([-60.0, 30.0])

    ds = convert_tracers_to_mpas_ocean(ds, lon=lon, lat=lat)

    # check a single valid (cell, level) against a direct gsw call
    expected_sp = gsw.SP_from_SA(sa[0, 1, 0], p_dbar[0, 1, 0], lon[1], lat[1])
    assert_allclose(ds.salinity.values[0, 1, 0], expected_sp)
