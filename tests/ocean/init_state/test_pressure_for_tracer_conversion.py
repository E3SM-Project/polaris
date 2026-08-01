from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.init_state import pressure_for_tracer_conversion
from polaris.ocean.vertical.ztilde import (
    get_iter_count_for_eos,
    pressure_and_spec_vol_from_state_at_geom_height,
)


def _make_config(eos_type='teos-10'):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'eos_type', eos_type)
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'pseudothickness_iter_count', '4')
    return config


def _make_state_ds(surface_pressure=None):
    """A 2-cell, 3-layer dataset with the fields needed to compute a
    pressure."""
    data_vars: dict = dict(
        layerThickness=(
            ('Time', 'nCells', 'nVertLevels'),
            10.0 * np.ones((1, 2, 3)),
        ),
        temperature=(
            ('Time', 'nCells', 'nVertLevels'),
            np.array([[[10.0, 8.0, 6.0], [12.0, 10.0, 8.0]]]),
        ),
        salinity=(
            ('Time', 'nCells', 'nVertLevels'),
            np.array([[[35.0, 35.1, 35.2], [34.8, 34.9, 35.0]]]),
        ),
    )
    if surface_pressure is not None:
        data_vars['SurfacePressure'] = (
            ('Time', 'nCells'),
            np.array([surface_pressure]),
        )
    return xr.Dataset(data_vars=data_vars)


def _expected_pressure(ds, config, surf_pressure):
    _, p_mid, _ = pressure_and_spec_vol_from_state_at_geom_height(
        config=config,
        geom_layer_thickness=ds.layerThickness,
        temperature=ds.temperature,
        salinity=ds.salinity,
        surf_pressure=surf_pressure,
        iter_count=get_iter_count_for_eos(config),
    )
    return p_mid


def test_pressure_for_tracer_conversion_uses_existing_pressure():
    ds = _make_state_ds()
    ds['pressure'] = 1.0e6 * xr.ones_like(ds.layerThickness)

    pressure = pressure_for_tracer_conversion(ds, _make_config())

    xr.testing.assert_identical(pressure, ds['pressure'])


def test_pressure_for_tracer_conversion_computes_from_thickness():
    config = _make_config()
    ds = _make_state_ds()

    pressure = pressure_for_tracer_conversion(ds, config)

    expected = _expected_pressure(
        ds, config, xr.zeros_like(ds.layerThickness.isel(nVertLevels=0))
    )
    assert_allclose(pressure.values, expected.values)
    assert pressure.dims == ds.layerThickness.dims
    # the pressure increases with depth from a zero surface pressure
    assert (np.diff(pressure.values, axis=-1) > 0.0).all()
    assert (pressure.values[..., 0] > 0.0).all()


def test_pressure_for_tracer_conversion_uses_surface_pressure():
    config = _make_config()
    ds = _make_state_ds(surface_pressure=[1.0e5, 2.0e5])

    pressure = pressure_for_tracer_conversion(ds, config)

    expected = _expected_pressure(ds, config, ds.SurfacePressure)
    assert_allclose(pressure.values, expected.values)

    without = pressure_for_tracer_conversion(_make_state_ds(), config)
    # the surface pressure shifts the whole column
    assert (pressure.values > without.values).all()


@pytest.mark.parametrize(
    'missing_var', ['layerThickness', 'temperature', 'salinity']
)
def test_pressure_for_tracer_conversion_raises_when_missing(missing_var):
    ds = _make_state_ds().drop_vars(missing_var)

    with pytest.raises(ValueError, match=missing_var):
        pressure_for_tracer_conversion(ds, _make_config())
