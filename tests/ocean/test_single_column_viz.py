"""
Tests for the single-column plotting helpers.

Plotting a field defined at layer interfaces used to raise an ``IndexError``:
the field was trimmed to mid-level length with ``isel()``, which changes the
length of the dimension but not its name, and the x-axis range was then built
from a mask on ``nVertLevels``.
"""

import numpy as np
import xarray as xr

from polaris.tasks.ocean.single_column.viz import (
    _add_visible_limits,
    _interfaces_to_mid_levels,
)


def _interface_field(values):
    return xr.DataArray(np.array(values), dims=('nVertLevelsP1',))


def _mid_level_field(values):
    return xr.DataArray(np.array(values), dims=('nVertLevels',))


def test_interface_field_is_trimmed_and_renamed():
    var = _interfaces_to_mid_levels(_interface_field([1.0, 2.0, 3.0, 4.0]))
    assert var.dims == ('nVertLevels',)
    assert var.sizes['nVertLevels'] == 3
    np.testing.assert_array_equal(var.values, [1.0, 2.0, 3.0])


def test_a_mid_level_field_is_left_alone():
    original = _mid_level_field([1.0, 2.0, 3.0])
    var = _interfaces_to_mid_levels(original)
    assert var.dims == ('nVertLevels',)
    np.testing.assert_array_equal(var.values, original.values)


def test_a_trimmed_interface_field_can_be_masked_by_depth():
    # this is the combination that used to raise an IndexError
    z_mid = _mid_level_field([-10.0, -60.0, -150.0])
    var = _interfaces_to_mid_levels(_interface_field([1.0, 2.0, 3.0, 4.0]))
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z_mid, -100.0, 0.0)
    assert x_limits == [(1.0, 2.0)]


def test_depths_outside_the_plot_are_excluded():
    z_mid = _mid_level_field([-10.0, -50.0, -300.0])
    var = _mid_level_field([1.0, 2.0, 99.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z_mid, -100.0, 0.0)
    assert x_limits == [(1.0, 2.0)]


def test_nans_are_ignored():
    z_mid = _mid_level_field([-10.0, -50.0])
    var = _mid_level_field([np.nan, 2.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z_mid, -100.0, 0.0)
    assert x_limits == [(2.0, 2.0)]


def test_an_all_nan_profile_adds_nothing():
    z_mid = _mid_level_field([-10.0, -50.0])
    var = _mid_level_field([np.nan, np.nan])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z_mid, -100.0, 0.0)
    assert x_limits == []


def test_a_profile_with_nothing_visible_adds_nothing():
    z_mid = _mid_level_field([-300.0, -400.0])
    var = _mid_level_field([1.0, 2.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(x_limits, var, z_mid, -100.0, 0.0)
    assert x_limits == []


def test_limits_accumulate_over_several_curves():
    # the x range has to cover every curve drawn, not just the last one
    z_mid = _mid_level_field([-10.0, -50.0])
    x_limits: list[tuple[float, float]] = []
    _add_visible_limits(
        x_limits, _mid_level_field([1.0, 2.0]), z_mid, -100.0, 0.0
    )
    _add_visible_limits(
        x_limits, _mid_level_field([-5.0, 0.0]), z_mid, -100.0, 0.0
    )
    assert min(limits[0] for limits in x_limits) == -5.0
    assert max(limits[1] for limits in x_limits) == 2.0
