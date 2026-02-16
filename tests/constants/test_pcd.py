import pytest

from polaris.constants.pcd import get_constant


@pytest.mark.parametrize(
    'name, expected',
    [
        ('pi', 3.141592653589793238462643),
        ('speed_of_light_in_vacuum', 299792458),
        ('total_solar_irradiance', 1360.8),
        ('water_triple_point_pressure', 611.655),
    ],
)
def test_get_constant_expected_values(name, expected):
    value = get_constant(name)
    if isinstance(expected, float):
        assert value == pytest.approx(expected)
    else:
        assert value == expected


def test_get_constant_missing_returns_none():
    assert get_constant('dummy_constant_that_does_not_exist') is None
