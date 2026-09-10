import numpy as np
import pytest
from numpy.testing import assert_allclose

from polaris.mpas.time import time_index_from_xtime, time_since_start

# the times the test datasets sample, and the seconds since the first of
# them
XTIME = np.array(
    [
        b'0001-01-01_00:00:00',
        b'0001-01-02_12:00:00',
        b'0001-01-11_06:00:00',
    ]
)

SECONDS = np.array([0.0, 129600.0, 885600.0])


def test_default_start_is_first_entry():
    """The default start time is the first entry in ``xtime``, so the
    first time is zero rather than an offset from a fixed date."""
    assert_allclose(time_since_start(XTIME), SECONDS)


def test_explicit_start_is_honored():
    """An explicit start time shifts the whole series."""
    dt = time_since_start(XTIME, start_xtime='0001-01-01_01:00:00')
    assert_allclose(dt, SECONDS - 3600.0)


def test_decimal_seconds_format():
    """Times written with decimal seconds still parse."""
    xtime = np.array([b'0001-01-01_00:00:00.00', b'0001-01-01_00:00:01.50'])
    assert_allclose(time_since_start(xtime), [0.0, 1.5])


@pytest.mark.parametrize(
    ('dt_target', 'expected'), [(0.0, 0), (129600.0, 1), (1.0e6, 2)]
)
def test_time_index_from_xtime(dt_target, expected):
    """The index closest to the target is measured from the first time."""
    assert time_index_from_xtime(XTIME, dt_target) == expected
