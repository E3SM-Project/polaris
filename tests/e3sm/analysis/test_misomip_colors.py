import numpy as np
import pytest

from polaris.tasks.e3sm.analysis.misomip.colors import (
    get_signed_colors,
    get_signed_range,
)


@pytest.mark.parametrize('kind', ['melt', 'thermal_driving'])
@pytest.mark.parametrize('vmin', [0.0, -0.1, -50.0])
def test_zero_is_a_tenth_of_the_way_up_the_bar(kind, vmin):
    """At least 90% of the bar is positive, however far below zero the
    values reach, and a negative value never has zero's color"""
    cmap, norm, ticks = get_signed_colors(kind, vmin, 8.0)
    assert float(norm(0.0)) == pytest.approx(0.1)
    assert float(norm(8.0)) == pytest.approx(1.0)
    assert ticks[0] < 0.0 and ticks[1] > 0.0 and ticks[-1] <= 8.0
    assert ticks[0] <= vmin
    assert not np.allclose(cmap(float(norm(-0.05))), cmap(float(norm(0.0))))


def test_melt_colors_are_continuous_through_zero():
    cmap, norm, _ = get_signed_colors('melt', -0.5, 9.0)
    below = np.array(cmap(float(norm(-0.01))))
    at_zero = np.array(cmap(float(norm(0.0))))
    assert np.max(np.abs(below - at_zero)) < 0.05


def test_small_negative_values_keep_the_bar_linear():
    _, norm, _ = get_signed_colors('melt', -0.1, 9.0)
    assert float(norm(-0.5)) == pytest.approx(0.05)


def test_the_range_always_contains_zero():
    assert get_signed_range([np.array([1.0, 2.0, np.nan])])[0] == 0.0
    assert get_signed_range([np.array([-2.0, -1.0])])[1] == 0.0
