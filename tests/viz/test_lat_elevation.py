"""
Unit tests for the latitude-elevation contour plot.

What these check is what a reader would be misled by if it were wrong: which
way up the elevation axis runs, which orientation of the field is drawn, where
the contour lines fall, and whether the color bar's arrows are claiming data
that is not there.  They reach into the figure rather than comparing images,
so that a failure says what broke.
"""

import os

import numpy as np
import pytest
import xarray as xr
from matplotlib.contour import ContourSet
from matplotlib.figure import Figure

from polaris.config import PolarisConfigParser
from polaris.viz.lat_elevation import (
    _contour_levels,
    _extend,
    _latitude_ticks,
    _oriented_values,
    plot_lat_elevation_field,
)

LAT = np.linspace(-89.5, 89.5, 60)
Z = np.linspace(-5000.0, 0.0, 41)


def _config(**options):
    """A config with the color map the MOC plot is drawn with"""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean_analysis_moc', 'colormap_name', 'cmo.balance')
    config.set('ocean_analysis_moc', 'norm_type', 'linear')
    config.set('ocean_analysis_moc', 'norm_args', '{}')
    for option, value in options.items():
        config.set('ocean_analysis_moc', option, value)
    return config


def _field(amplitude=20.0):
    """A two-celled streamfunction-like field, zero at the boundaries"""
    values = (
        amplitude
        * np.sin(2.0 * np.pi * (LAT[np.newaxis, :] + 90.0) / 180.0)
        * np.sin(np.pi * (Z[:, np.newaxis] + 5000.0) / 5000.0)
    )
    return xr.DataArray(values, dims=('nz', 'nlat'))


def _plot(tmp_path, da=None, name='field.png', **kwargs):
    """Draw the plot and give back the file it wrote"""
    if da is None:
        da = _field()
    out_filename = str(tmp_path / name)
    kwargs.setdefault('config', _config())
    kwargs.setdefault('colormap_section', 'ocean_analysis_moc')
    plot_lat_elevation_field(
        da=da, lat=LAT, z=Z, out_filename=out_filename, **kwargs
    )
    return out_filename


def _figure_of(monkeypatch, da=None, **kwargs):
    """Draw the plot and give back the figure rather than the file"""
    if da is None:
        da = _field()
    figures: list = []
    monkeypatch.setattr(
        Figure, 'savefig', lambda self, *args, **inner: figures.append(self)
    )
    kwargs.setdefault('config', _config())
    kwargs.setdefault('colormap_section', 'ocean_analysis_moc')
    plot_lat_elevation_field(
        da=da, lat=LAT, z=Z, out_filename='not written', **kwargs
    )
    return figures[0]


def _contour_sets(figure):
    """The filled contours, and the lines over them if there are any"""
    return [
        child
        for child in figure.axes[0].get_children()
        if isinstance(child, ContourSet)
    ]


def test_the_plot_is_written(tmp_path):
    filename = _plot(tmp_path, contour_interval=5.0, max_abs=20.0)
    assert os.path.getsize(filename) > 0


def test_the_sea_surface_is_at_the_top_without_inverting_the_axis(
    monkeypatch,
):
    """Elevation is positive up, so the surface is at the top of an axis
    that increases upwards.  Inverting the axis instead would put the surface
    at the top while labelling it backwards."""
    axes = _figure_of(monkeypatch, max_abs=20.0).axes[0]
    bottom, top = axes.get_ylim()
    assert bottom < top
    assert bottom == pytest.approx(Z.min())
    assert top == pytest.approx(Z.max())


def test_either_orientation_of_the_field_draws_the_same_plot(tmp_path):
    """A field given as (latitude, elevation) is transposed rather than
    refused, since which way round it comes depends on what wrote it."""
    da = _field()
    one = _plot(tmp_path, da=da, name='one.png', max_abs=20.0)
    other = _plot(tmp_path, da=da.transpose(), name='other.png', max_abs=20.0)
    with open(one, 'rb') as first, open(other, 'rb') as second:
        assert first.read() == second.read()


def test_a_field_that_fits_neither_way_is_reported(tmp_path):
    da = xr.DataArray(np.zeros((3, 4)), dims=('nz', 'nlat'))
    with pytest.raises(ValueError, match='cannot be plotted against'):
        _plot(tmp_path, da=da)


def test_oriented_values_puts_elevation_down_the_rows():
    da = _field()
    values = _oriented_values(da, lat=LAT, z=Z)
    assert values.shape == (len(Z), len(LAT))
    assert np.array_equal(values, da.values)
    assert np.array_equal(
        _oriented_values(da.transpose(), lat=LAT, z=Z), da.values
    )


def test_a_square_field_is_taken_as_elevation_then_latitude():
    """Nothing in the shape tells the two apart, so the dimension order the
    caller gave is used rather than a guess."""
    lat = np.linspace(-80.0, 80.0, 5)
    z = np.linspace(-4000.0, 0.0, 5)
    values = np.arange(25.0).reshape(5, 5)
    da = xr.DataArray(values, dims=('nz', 'nlat'))
    assert np.array_equal(_oriented_values(da, lat=lat, z=z), values)


def test_contour_lines_are_multiples_of_the_interval():
    levels = _contour_levels(4.0, np.linspace(-11.0, 7.5, 100))
    assert np.array_equal(levels, [-8.0, -4.0, 0.0, 4.0])


def test_contour_lines_reach_the_ends_of_the_data():
    """A color map clipped to bring out a weak circulation still gets lines
    through the saturated part of it, which is the only thing left there that
    says how strong the strong part is."""
    levels = _contour_levels(10.0, np.linspace(-20.0, 20.0, 100))
    assert np.array_equal(levels, [-20.0, -10.0, 0.0, 10.0, 20.0])


def test_the_lines_that_are_drawn_are_the_ones_asked_for(monkeypatch):
    """The same, end to end: a color map clipped to 5 Sv over a field that
    runs to nearly 20 still carries lines through the saturated part."""
    figure = _figure_of(monkeypatch, max_abs=5.0, contour_interval=10.0)
    filled, lines = _contour_sets(figure)
    assert filled.levels[0] == pytest.approx(-5.0)
    assert filled.levels[-1] == pytest.approx(5.0)
    assert np.allclose(lines.levels, [-10.0, 0.0, 10.0])
    # the lines run past the ends of the color map, which is the point
    assert max(abs(lines.levels)) > filled.levels[-1]


def test_no_contour_interval_draws_no_contour_lines(monkeypatch):
    assert len(_contour_sets(_figure_of(monkeypatch, max_abs=20.0))) == 1


def test_a_field_with_no_valid_values_gets_no_contour_lines():
    assert len(_contour_levels(2.0, np.full(10, np.nan))) == 0


def test_a_field_between_two_levels_gets_no_contour_lines():
    assert len(_contour_levels(10.0, np.linspace(1.0, 9.0, 10))) == 0


def test_a_contour_interval_must_be_positive():
    with pytest.raises(ValueError, match='must be positive'):
        _contour_levels(0.0, np.linspace(-1.0, 1.0, 10))


def test_contour_levels_ignore_what_is_below_the_seafloor():
    values = np.array([np.nan, -3.0, 1.0, np.nan])
    assert np.array_equal(_contour_levels(2.0, values), [-2.0, 0.0])


def test_the_color_bar_points_only_where_there_is_data_beyond_it():
    values = np.linspace(-5.0, 5.0, 21)
    assert _extend(values, -10.0, 10.0) == 'neither'
    assert _extend(values, -1.0, 10.0) == 'min'
    assert _extend(values, -10.0, 1.0) == 'max'
    assert _extend(values, -1.0, 1.0) == 'both'
    assert _extend(np.full(5, np.nan), -1.0, 1.0) == 'neither'


def test_latitude_ticks_are_round_numbers_inside_the_data():
    assert np.array_equal(
        _latitude_ticks(np.array([-89.5, 89.5])),
        [-60.0, -30.0, 0.0, 30.0, 60.0],
    )
    assert np.array_equal(
        _latitude_ticks(np.array([-90.0, 90.0])),
        [-90.0, -60.0, -30.0, 0.0, 30.0, 60.0, 90.0],
    )


def test_a_narrow_latitude_range_still_gets_ticks():
    """A basin that no multiple of the spacing falls inside would otherwise
    be left with an unlabelled axis."""
    assert np.array_equal(_latitude_ticks(np.array([1.0, 20.0])), [1.0, 20.0])


def test_max_abs_centers_the_color_map_on_zero(monkeypatch):
    filled = _contour_sets(_figure_of(monkeypatch, max_abs=12.0))[0]
    assert filled.norm.vmin == pytest.approx(-12.0)
    assert filled.norm.vmax == pytest.approx(12.0)


def test_without_max_abs_the_color_map_comes_from_the_config(monkeypatch):
    """A field with no natural center sets its own limits, the way every
    other plot in polaris.viz does."""
    config = _config(norm_args="{'vmin': -4., 'vmax': 8.}")
    filled = _contour_sets(_figure_of(monkeypatch, config=config))[0]
    assert filled.norm.vmin == pytest.approx(-4.0)
    assert filled.norm.vmax == pytest.approx(8.0)


def test_an_unbounded_color_map_scales_to_the_data(monkeypatch):
    """An empty norm_args and no max_abs is the ordinary autoscaling case,
    and it has to survive the values below the seafloor being NaN."""
    da = _field()
    values = da.values.copy()
    values[0, :] = np.nan
    filled = _contour_sets(
        _figure_of(monkeypatch, da=xr.DataArray(values, dims=da.dims))
    )[0]
    finite = values[np.isfinite(values)]
    assert filled.norm.vmin == pytest.approx(finite.min())
    assert filled.norm.vmax == pytest.approx(finite.max())
