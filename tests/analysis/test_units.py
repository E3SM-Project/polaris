"""
Unit tests for rendering a CF ``units`` attribute as matplotlib text.

The spellings are the ones Omega writes today (E3SM-Project/Omega#544), so
that a label made from any of them renders with a superscript rather than a
bare ``-2``, and what is not a units string at all is left alone.
"""

import pytest
from matplotlib.mathtext import MathTextParser

from polaris.analysis.units import units_to_mathtext

# every spelling of an exponent that Omega writes, and the CF one
EXPONENTS = [
    ('kg m-2 s-1', 'kg m$^{-2}$ s$^{-1}$'),
    ('m^-1 s^-1', 'm$^{-1}$ s$^{-1}$'),
    ('N m^{-2}', 'N m$^{-2}$'),
    ('m**-2', 'm$^{-2}$'),
    ('m2', 'm$^{2}$'),
    ('m3 kg-1', 'm$^{3}$ kg$^{-1}$'),
    ('g kg-1', 'g kg$^{-1}$'),
]


@pytest.mark.parametrize('units, expected', EXPONENTS)
def test_an_exponent_becomes_a_superscript(units, expected):
    assert units_to_mathtext(units) == expected


def test_a_slash_divides_by_what_follows_it():
    assert units_to_mathtext('m/s') == 'm s$^{-1}$'
    assert units_to_mathtext('m/s^2') == 'm s$^{-2}$'
    assert units_to_mathtext('J/(m2 s)') == 'J m$^{-2}$ s$^{-1}$'


def test_degrees_are_a_sign():
    assert units_to_mathtext('degree_C') == r'$^\circ$C'
    assert units_to_mathtext('degC') == r'$^\circ$C'
    assert units_to_mathtext('degrees_north') == r'$^\circ$N'


def test_a_dimensionless_quantity_has_nothing_to_print():
    for units in ('', '1', 'dimensionless'):
        assert units_to_mathtext(units) == ''


def test_a_symbol_without_an_exponent_is_itself():
    for units in ('m', 'Pa', 'Sv', 'radians', 'years', '%'):
        assert units_to_mathtext(units) == units
    assert units_to_mathtext('1e6 m3 s-1') == '1e6 m$^{3}$ s$^{-1}$'


def test_what_is_not_recognized_is_left_alone():
    """Guessing would put a wrong label on a plot; the raw string is at
    least honest."""
    assert units_to_mathtext('tracer units') == 'tracer units'
    assert units_to_mathtext('seconds since 0001-01-01') == (
        'seconds since 0001-01-01'
    )


def test_mathtext_is_already_rendered():
    assert units_to_mathtext(r'kg/m$^3$') == r'kg/m$^3$'


@pytest.mark.parametrize(
    'units',
    [units for units, _ in EXPONENTS]
    + ['m/s', 'J/(m2 s)', 'degree_C', 'degrees_north', '1e6 m3 s-1'],
)
def test_the_result_is_valid_mathtext(units):
    """What matplotlib would raise on when the plot is drawn is raised
    here instead."""
    MathTextParser('agg').parse(units_to_mathtext(units))
