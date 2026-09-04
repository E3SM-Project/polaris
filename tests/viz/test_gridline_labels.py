"""
Unit tests for the room a spherical plot leaves for its gridline labels.

Cartopy draws gridline labels outside the axes, and a ``GeoAxes`` reports a
non-finite tight bounding box, so the layout engine reserves no room for them
and they are drawn off the canvas: the outermost longitude label is cut in
half and every latitude label is lost entirely.  These check that the axes
report a finite bounding box and that every label lands inside the figure.

They run in the Polaris style, since that is what sets the figure size and
label size the plots are actually drawn with.
"""

import cartopy.crs as ccrs
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from polaris.viz.helper import get_projection, make_room_for_gridline_labels
from polaris.viz.style import mplstyle_context

# a rectangular projection, one with a curved boundary, an interrupted one and
# a polar one, since where cartopy puts a label depends on the boundary
PROJECTIONS = [
    'PlateCarree',
    'Robinson',
    'InterruptedGoodeHomolosine',
    'NorthPolarStereo',
]


def _figure(projection_name, make_room):
    """Build the figure that ``plot_global_mpas_field()`` builds"""
    projection = get_projection(projection_name)
    fig = Figure(figsize=(8, 4.5), constrained_layout=True)
    # measuring rendered labels needs a canvas that can produce a renderer;
    # a bare figure carries one that cannot
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111, projection=projection)
    ax.set_global()
    gl = ax.gridlines(color='gray', linestyle=':', zorder=5, draw_labels=True)
    gl.right_labels = False
    gl.top_labels = False
    if make_room:
        make_room_for_gridline_labels(ax)

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
        fig, ax, gl = _figure(projection_name, make_room=True)
        # a non-finite box is what makes the layout engine reserve nothing
        bbox = ax.get_tightbbox(fig.canvas.get_renderer())
        assert np.isfinite([bbox.x0, bbox.y0, bbox.x1, bbox.y1]).all()
        assert _cropped_labels(fig, gl) == []


def test_labels_are_cropped_without_the_fix():
    """The bug this guards against, so the tests above cannot pass vacuously"""
    with mplstyle_context():
        fig, ax, gl = _figure('PlateCarree', make_room=False)
        assert _cropped_labels(fig, gl)
