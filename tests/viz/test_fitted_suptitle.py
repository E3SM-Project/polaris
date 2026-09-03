"""
Unit tests for the figure title that fits the figure.

A title wider than the figure is cropped when the figure is saved at a fixed
size, and what it loses is what distinguishes one plot from another.  These
check that it is made to fit, and that nothing is dropped to do it.

They run in the Polaris style, since that is what sets the title size the
plots are actually drawn with.
"""

from matplotlib.figure import Figure

from polaris.viz.helper import add_fitted_suptitle
from polaris.viz.style import mplstyle_context

SHORT = 'qu240: ssh, ANN'
LONG = (
    'qu240_mockup: ocean heat content, -2000m to bottom, ANN, years 0001-0001'
)
ABSURD = (
    'qu240_mockup: ocean heat content over the deep ocean from -2000 m to '
    'the seafloor, annual mean, simulation years 0001-0001, on the native '
    'unstructured mesh with no remapping of any kind applied to it'
)


def _figure():
    fig = Figure(figsize=(8, 4.5), constrained_layout=True)
    fig.add_subplot(111)
    return fig


def _default_fontsize(fig, title):
    text = fig.suptitle(title)
    size = text.get_fontsize()
    text.remove()
    return size


def _fits(fig, text):
    renderer = fig.canvas.get_renderer()
    width = text.get_window_extent(renderer=renderer).width
    return width <= fig.get_size_inches()[0] * fig.dpi


def test_a_title_that_fits_is_left_alone():
    with mplstyle_context():
        fig = _figure()
        default = _default_fontsize(fig, SHORT)
        text = add_fitted_suptitle(fig, SHORT)
        assert text.get_fontsize() == default
        assert _fits(fig, text)


def test_a_long_title_is_shrunk_until_it_fits():
    with mplstyle_context():
        fig = _figure()
        default = _default_fontsize(fig, LONG)
        text = add_fitted_suptitle(fig, LONG)
        assert text.get_fontsize() < default
        assert '\n' not in text.get_text()
        assert _fits(fig, text)


def test_a_title_too_long_to_shrink_is_wrapped():
    with mplstyle_context():
        fig = _figure()
        text = add_fitted_suptitle(fig, ABSURD)
        assert '\n' in text.get_text()
        assert _fits(fig, text)


def test_no_title_loses_any_of_its_words():
    """Fitting must not drop what tells two plots apart."""
    with mplstyle_context():
        for title in (SHORT, LONG, ABSURD):
            fig = _figure()
            text = add_fitted_suptitle(fig, title)
            assert text.get_text().split() == title.split()
