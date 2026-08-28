import numpy as np
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.init_state import (
    add_density_from_specvol,
    add_quiescent_normal_velocity,
    layer_thickness_from_geom_interfaces,
)

# Attributes that ride in from the combined topography and must not survive
# onto anything derived from a geometric height.
TOPO_ATTRS = {'unit': 'meters', 'cell_measures': 'area: area'}


def _make_geom_ds(geom_attrs=None):
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
    ds = xr.Dataset(
        data_vars=dict(
            GeomZInterface=(
                ('Time', 'nCells', 'nVertLevelsP1'),
                geom_z_inter,
            ),
            cellMask=(('nCells', 'nVertLevels'), cell_mask),
        )
    )
    if geom_attrs is not None:
        ds.GeomZInterface.attrs = dict(geom_attrs)
    return ds


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


def test_layer_thickness_does_not_inherit_geom_attrs():
    """The thicknesses say only what they mean.

    They are computed by differencing GeomZInterface, which arrives carrying
    whatever the topography chain put on it.
    """
    ds = _make_geom_ds(geom_attrs=TOPO_ATTRS)
    ds = layer_thickness_from_geom_interfaces(ds)

    expected = {
        'restingThickness': 'resting layer thickness',
        'layerThickness': 'layer thickness',
    }
    for var, long_name in expected.items():
        assert ds[var].attrs == {'long_name': long_name, 'units': 'm'}


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
