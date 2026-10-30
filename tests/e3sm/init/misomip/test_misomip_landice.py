import numpy as np
import pytest

from polaris.tasks.e3sm.init.misomip.calving import (
    calve,
    get_floating_mask,
    get_grounded_mask,
)
from polaris.tasks.e3sm.init.misomip.records import (
    SECONDS_PER_DAY,
    get_interpolation_weights,
    get_monthly_record_times,
)


def test_floating_and_grounded_masks():
    # densities whose ratio is exact, so 1800 m of ice is exactly at
    # flotation on a bed 900 m deep
    densities = dict(ice_density=500.0, ocean_density=1000.0)
    bed = np.array([-900.0, -900.0, -900.0, -900.0, 100.0])
    thickness = np.array([0.0, 500.0, 1800.0, 2000.0, 50.0])
    floating = get_floating_mask(thickness, bed, **densities)
    grounded = get_grounded_mask(thickness, bed, **densities)
    # ice exactly at flotation floats, as in MALI
    np.testing.assert_array_equal(floating, [False, True, True, False, False])
    np.testing.assert_array_equal(grounded, [False, False, False, True, True])


def test_calve_thin_floating_ice():
    bed = np.array([-900.0, -900.0, -50.0, -900.0, -900.0])
    thickness = np.array([99.0, 100.0, 99.0, 500.0, 500.0])
    x_cell = np.array([500.0e3, 500.0e3, 500.0e3, 640.0e3, 641.0e3])
    calved = calve(thickness, bed, x_cell)
    # thin floating ice and any ice beyond 640 km go; thin grounded ice and
    # ice at 100 m stay
    np.testing.assert_array_equal(calved, [0.0, 100.0, 99.0, 500.0, 0.0])


def test_calve_with_time_records():
    bed = np.array([-900.0, -900.0])
    thickness = np.array([[50.0, 500.0], [500.0, 50.0]])
    x_cell = np.array([400.0e3, 400.0e3])
    calved = calve(thickness, bed, x_cell)
    np.testing.assert_array_equal(calved, [[0.0, 500.0], [500.0, 0.0]])


def test_monthly_record_times():
    xtimes, seconds = get_monthly_record_times(year_count=100)
    assert len(xtimes) == 1201
    assert xtimes[0] == '0001-01-01_00:00:00'
    assert xtimes[1] == '0001-02-01_00:00:00'
    assert xtimes[12] == '0002-01-01_00:00:00'
    assert xtimes[-1] == '0101-01-01_00:00:00'
    assert seconds[0] == 0.0
    assert seconds[1] == 31.0 * SECONDS_PER_DAY
    assert seconds[12] == 365.0 * SECONDS_PER_DAY
    # the protocol's last yearly record, in seconds
    assert seconds[-1] == 3153600000.0
    assert np.all(np.diff(seconds) > 0.0)


def test_interpolation_weights():
    yearly = 365.0 * SECONDS_PER_DAY * np.arange(101)
    _, seconds = get_monthly_record_times(year_count=100)
    before, after, weight = get_interpolation_weights(seconds, yearly)

    # the start of each year is a yearly record
    np.testing.assert_array_equal(before[::12], np.arange(101).clip(max=99))
    np.testing.assert_allclose(weight[:-1:12], 0.0)
    assert weight[-1] == 1.0
    assert after[-1] == 100

    # the start of February is 31 days into the first year
    assert before[1] == 0
    assert after[1] == 1
    assert weight[1] == pytest.approx(31.0 / 365.0)

    assert np.all(weight >= 0.0)
    assert np.all(weight <= 1.0)


def test_interpolation_weights_outside_the_records():
    with pytest.raises(ValueError):
        get_interpolation_weights(np.array([2.0]), np.array([0.0, 1.0]))
