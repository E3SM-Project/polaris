"""
Unit tests for the room a spherical plot leaves around its map.

Cartopy draws gridline labels outside the axes, so the layout engine only
reserves room for them if the axes report a finite tight bounding box.  Before
cartopy 0.26, a ``GeoAxes`` reported a non-finite one and the labels were
drawn off the canvas: the outermost longitude label was cut in half and every
latitude label was lost entirely.  These check that the axes report a finite
bounding box, that every label lands inside the figure, and that the title
clears the map rather than being drawn over it.

They run in the Polaris style, since that is what sets the figure size and
label size the plots are actually drawn with.
"""

import cartopy.crs as ccrs
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from polaris.viz.helper import add_fitted_suptitle, get_projection
from polaris.viz.style import mplstyle_context

# a rectangular projection, one with a curved boundary, an interrupted one and
# a polar one, since where cartopy puts a label depends on the boundary
PROJECTIONS = [
    'PlateCarree',
    'Robinson',
    'InterruptedGoodeHomolosine',
    'NorthPolarStereo',
]


def _figure(projection_name, figsize=(8, 4.5), title=None, title_y=None):
    """Build the figure that ``plot_global_mpas_field()`` builds"""
    projection = get_projection(projection_name)
    fig = Figure(figsize=figsize, constrained_layout=True)
    # measuring rendered labels needs a canvas that can produce a renderer;
    # a bare figure carries one that cannot
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111, projection=projection)
    ax.set_global()
    if title is not None:
        add_fitted_suptitle(fig, title, y=title_y)
    gl = ax.gridlines(color='gray', linestyle=':', zorder=5, draw_labels=True)
    gl.right_labels = False
    gl.top_labels = False

    lon = np.linspace(-180.0, 180.0, 13)
    lat = np.linspace(-90.0, 90.0, 7)
    field = np.zeros((lat.shape[0] - 1, lon.shape[0] - 1))
    pc = ax.pcolormesh(lon, lat, field, transform=ccrs.PlateCarree(), zorder=1)
    fig.colorbar(pc, ax=ax, label='', extend='both', shrink=0.6)
    fig.canvas.draw()
    return fig, ax, gl


def _cropped_labels(fig, gl):
    """The visible gridline labels that are not wholly inside the figure"""
    renderer = fig.canvas.get_renderer()
    cropped = []
    for artist in gl.label_artists:
        if not artist.get_visible():
            continue
        extent = artist.get_window_extent(renderer=renderer)
        if not fig.bbox.containsx(extent.x0) or not fig.bbox.containsx(
            extent.x1
        ):
            cropped.append(artist.get_text())
        elif not fig.bbox.containsy(extent.y0) or not fig.bbox.containsy(
            extent.y1
        ):
            cropped.append(artist.get_text())
    return cropped


@pytest.mark.parametrize('projection_name', PROJECTIONS)
def test_no_gridline_label_is_cropped(projection_name):
    with mplstyle_context():
        fig, ax, gl = _figure(projection_name)
        # a non-finite box is what makes the layout engine reserve nothing
        bbox = ax.get_tightbbox(fig.canvas.get_renderer())
        assert np.isfinite([bbox.x0, bbox.y0, bbox.x1, bbox.y1]).all()
        assert _cropped_labels(fig, gl) == []


# the default figure is wider than a global map is tall, so a title placed a
# fixed distance from the top of the canvas happens to clear the map; a figure
# sized to a taller projection is where that goes wrong
@pytest.mark.parametrize('figsize', [(8, 4.5), (8, 6.4)])
def test_the_title_clears_the_map(figsize):
    with mplstyle_context():
        fig, ax, _ = _figure('Mercator', figsize=figsize, title='a title')
        renderer = fig.canvas.get_renderer()
        title = fig._suptitle.get_window_extent(renderer=renderer)
        assert title.ymin >= ax.get_window_extent(renderer).ymax
        assert title.ymax <= fig.bbox.y1


def test_a_title_at_a_fixed_height_lands_on_the_map():
    """The bug the test above guards against: a hand-placed title is one the
    layout engine does not reserve room for, so a figure sized to a taller
    projection draws it over the map.  0.935 is where the title used to be
    pinned."""
    with mplstyle_context():
        fig, ax, _ = _figure(
            'Mercator',
            figsize=(8, 6.4),
            title='a title',
            title_y=0.935,
        )
        renderer = fig.canvas.get_renderer()
        title = fig._suptitle.get_window_extent(renderer=renderer)
        assert title.ymin < ax.get_window_extent(renderer).ymax
