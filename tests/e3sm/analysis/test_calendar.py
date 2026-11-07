import numpy as np
import pytest

from polaris.e3sm.analysis.calendar import month_start_days, xtime_to_days


def test_xtime_counts_days_from_the_start_of_year_1():
    """Days count from 0001-01-01 in the 365-day calendar, so year 0 and
    MALI's 5-digit years come before it."""
    assert xtime_to_days('0001-01-01_00:00:00') == 0.0
    assert xtime_to_days('0001-03-01_12:00:00') == 59.5
    assert xtime_to_days('0002-01-01_00:00:00') == 365.0
    assert xtime_to_days(b'00000-01-01_00:00:00') == -365.0
    np.testing.assert_allclose(
        xtime_to_days(['0001-01-02_06:00:00', '00100-01-01_00:00:00']),
        [1.25, 365.0 * 99],
    )


def test_a_month_starts_after_the_days_of_the_months_before_it():
    assert month_start_days(1, 1) == 0.0
    assert month_start_days(1, 13) == 365.0
    assert month_start_days(3, 2) == 2 * 365.0 + 31.0


def test_a_string_that_is_not_an_xtime_raises():
    with pytest.raises(ValueError, match='not an MPAS xtime'):
        xtime_to_days('2001-01-01')
