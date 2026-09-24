"""
Tests for the single-column plotting helpers.

A field defined at layer interfaces used to be trimmed to mid-level length
with ``isel()`` and plotted against ``zMid``, which put it half a layer below
where it is defined.  ``isel()`` also changes the length of a dimension but
not its name, so building the x-axis range from a mask on ``nVertLevels``
then raised an ``IndexError``.  Interface fields are now plotted against
``GeomZInterface``, which is both where they belong and the same dimension.

A field written at layer tops on ``nVertLevels`` cannot be told from a
layer average by its dimensions, so it is named in ``variables.yaml`` under
``variables_at_layer_tops`` and paired with the top interface of each layer
(``zTop``).
"""

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical.diagnostics import (
    location_for_field,
    vertical_coord_from_location,
)
from polaris.tasks.ocean.single_column.viz import _add_visible_limits

# a field the models agree is a layer quantity
MID = 'temperature'


def _vertical_coord(field_name, var, ds):
    location = location_for_field(var, field_name)
    return vertical_coord_from_location(ds, location)


def _interface_field(values):
    return xr.DataArray(np.array(values), dims=('nVertLevelsP1',))


def _mid_level_field(values):
    return xr.DataArray(np.array(values), dims=('nVertLevels',))


@pytest.fixture
def z_mid():
    return _mid_level_field([-10.0, -60.0, -150.0])


@pytest.fixture
def z_interface():
    return _interface_field([0.0, -20.0, -100.0, -200.0])


@pytest.fixture
def ds(z_mid, z_interface):
    z_top = _mid_level_field(z_interface.values[:-1])
    return xr.Dataset(
        data_vars=dict(zMid=z_mid, GeomZInterface=z_interface, zTop=z_top)
    )


def test_an_interface_field_is_plotted_at_interfaces(ds, z_interface):
    z = _vertical_coord(MID, _interface_field([1.0, 2.0, 3.0, 4.0]), ds)
    assert z.dims == ('nVertLevelsP1',)
    np.testing.assert_array_equal(z.values, z_interface.values)


def test_a_mid_level_field_is_plotted_at_midpoints(ds, z_mid):
    z = _vertical_coord(MID, _mid_level_field([1.0, 2.0, 3.0]), ds)
    assert z.dims == ('nVertLevels',)
    np.testing.assert_array_equal(z.values, z_mid.values)


def test_a_named_top_of_layer_field_is_plotted_at_layer_tops(ds, z_interface):
    # MPAS-Ocean writes BruntVaisalaFreqTop at layer tops but on
    # nVertLevels, so the dimensions alone would send it to zMid
    z = _vertical_coord(
        'BruntVaisalaFreqTop', _mid_level_field([1.0, 2.0, 3.0]), ds
    )
    assert z.dims == ('nVertLevels',)
    np.testing.assert_array_equal(z.values, z_interface.values[:-1])


def test_a_named_field_on_interfaces_is_left_on_interfaces(ds, z_interface):
    # Omega writes the same field on nVertLevelsP1; the dimensions win, so
    # naming a field is harmless for the model that gets it right
    z = _vertical_coord(
        'BruntVaisalaFreqTop', _interface_field([1.0, 2.0, 3.0, 4.0]), ds
    )
    assert z.dims == ('nVertLevelsP1',)
    np.testing.assert_array_equal(z.values, z_interface.values)


def test_an_interface_field_keeps_every_value(ds):
    # the bottom interface used to be dropped so that the field could be
    # plotted against zMid; nothing is dropped now
    var = _interface_field([1.0, 2.0, 3.0, 4.0])
    z = _vertical_coord(MID, var, ds)
    assert var.sizes['nVertLevelsP1'] == z.sizes['nVertLevelsP1']


def test_an_interface_field_can_be_masked_by_depth(ds):
    # this is the combination that used to raise an IndexError
    var = _interface_field([1.0, 2.0, 3.0, 4.0])
    z = _vertical_coord(MID, var, ds)
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == [(1.0, 3.0)]


def test_a_top_of_layer_field_can_be_masked_by_depth(ds):
    # the renamed coordinate has to match the field's own dimension
    var = _mid_level_field([1.0, 2.0, 3.0])
    z = _vertical_coord('BruntVaisalaFreqTop', var, ds)
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == [(1.0, 3.0)]


def test_depths_outside_the_plot_are_excluded():
    z = _mid_level_field([-10.0, -50.0, -300.0])
    var = _mid_level_field([1.0, 2.0, 99.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == [(1.0, 2.0)]


def test_nans_are_ignored():
    z = _mid_level_field([-10.0, -50.0])
    var = _mid_level_field([np.nan, 2.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == [(2.0, 2.0)]


def test_an_all_nan_profile_adds_nothing():
    z = _mid_level_field([-10.0, -50.0])
    var = _mid_level_field([np.nan, np.nan])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == []


def test_a_profile_with_nothing_visible_adds_nothing():
    z = _mid_level_field([-300.0, -400.0])
    var = _mid_level_field([1.0, 2.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z, -100.0, 0.0)
    assert x_limits == []


def test_limits_accumulate_over_several_curves():
    # the x range has to cover every curve drawn, not just the last one
    z = _mid_level_field([-10.0, -50.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, _mid_level_field([1.0, 2.0]), z, -100.0, 0.0)
    _add_visible_limits(
        x_limits, _mid_level_field([-5.0, 0.0]), z, -100.0, 0.0
    )
    assert min(limits[0] for limits in x_limits) == -5.0
    assert max(limits[1] for limits in x_limits) == 2.0


def test_curves_on_different_coordinates_share_one_range(ds):
    # a plot mixes an interface field with the mid-level initial state, so
    # each curve contributes on its own coordinate
    x_limits: list[tuple[float, float]] = []
    var = _interface_field([1.0, 2.0, 3.0, 4.0])
    _add_visible_limits(
        x_limits,
        var,
        _vertical_coord(MID, var, ds),
        -100.0,
        0.0,
    )
    var = _mid_level_field([-1.0, 0.5, 99.0])
    _add_visible_limits(
        x_limits,
        var,
        _vertical_coord(MID, var, ds),
        -100.0,
        0.0,
    )
    assert min(limits[0] for limits in x_limits) == -1.0
    assert max(limits[1] for limits in x_limits) == 3.0
