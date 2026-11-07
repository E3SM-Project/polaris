import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.plots import (
    get_label_units,
    scale_with_units,
)

SECONDS_PER_YEAR = 365.0 * 86400.0


@pytest.mark.parametrize(
    'scale, label, units',
    [
        (SECONDS_PER_YEAR * 1e-12, 'melt flux (Gt yr$^{-1}$)', 'Gt yr-1'),
        (1e-9, 'volume (km$^3$)', 'km3'),
        (100.0, 'height (cm)', 'cm'),
        (SECONDS_PER_YEAR, 'm yr$^{-1}$', 'm yr-1'),
    ],
)
def test_a_scaled_field_takes_the_plot_s_units(scale, label, units):
    """A melt flux in kg s-1 plotted in Gt/yr is written in Gt yr-1, and
    the other attributes are kept"""
    field = xr.DataArray(
        [1e5], dims='Time', attrs=dict(units='kg s-1', long_name='flux')
    )
    scaled = scale_with_units(field, scale, label)
    np.testing.assert_allclose(scaled, scale * 1e5)
    assert scaled.attrs == dict(units=units, long_name='flux')


def test_an_unscaled_field_keeps_its_units():
    field = xr.DataArray([1.0], dims='Time', attrs=dict(units='Sv'))
    assert scale_with_units(field, 1.0, 'range (Sv)').attrs['units'] == 'Sv'


@pytest.mark.parametrize(
    'label, units',
    [
        (r'temperature ($^\circ$C)', 'degC'),
        ('area (km$^2$)', 'km2'),
        ('fraction (%)', '%'),
        ('x (km)', 'km'),
    ],
)
def test_units_come_from_the_end_of_a_label(label, units):
    assert get_label_units(label) == units
