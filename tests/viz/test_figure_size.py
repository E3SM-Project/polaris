"""
Unit tests for sizing a spherical plot's figure to its map.

A map has a fixed aspect ratio, and a figure of the wrong shape has empty
canvas above and below it or to either side.  These check that the figure
takes the dimension it is given, that the map fills the other, and that the
labels, the title and the colorbar all land inside the figure, for a
rectangular projection, one with a curved boundary and a circular polar map.

They run in the Polaris style, since that is what sets the label size the
plots are actually drawn with.
"""

import cartopy.crs as ccrs
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from test_cull_mesh_to_cells import _quad_mesh_dataset

from polaris.config import PolarisConfigParser
from polaris.viz.helper import get_projection, make_room_for_gridline_labels
from polaris.viz.spherical import (
    _fit_figure_to_map,
    _set_circular_boundary,
    plot_global_mpas_field,
)
from polaris.viz.style import mplstyle_context

# a rectangular projection, one with a curved boundary and a polar one, since
# where cartopy puts a label depends on the boundary
PROJECTIONS = [
    ('PlateCarree', None),
    ('Robinson', None),
    ('NorthPolarStereo', (-180.0, 180.0, 60.0, 90.0)),
]

# how much of the figure the map may leave empty in the free dimension; the
# fit is to a hundredth of an inch, but the layout at the size settled on
# can differ from the one measured by a little more than that
EMPTY = 0.05


def _figure(projection_name, extent, title, fig_width, fig_height):
    """Build the figure ``plot_global_mpas_field()`` builds, and size it"""
    projection = get_projection(projection_name)
    fig = Figure(constrained_layout=True)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111, projection=projection)
    if extent is not None:
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        _set_circular_boundary(ax)
    gl = ax.gridlines(color='gray', linestyle=':', zorder=5, draw_labels=True)
    gl.right_labels = False
    gl.top_labels = False
    make_room_for_gridline_labels(ax)

    lon = np.linspace(-180.0, 180.0, 13)
    lat = np.linspace(-90.0, 90.0, 7)
    field = np.zeros((lat.shape[0] - 1, lon.shape[0] - 1))
    pc = ax.pcolormesh(lon, lat, field, transform=ccrs.PlateCarree(), zorder=1)
    cbar = fig.colorbar(
        pc, ax=ax, label='a colorbar label', extend='both', shrink=0.6
    )
    _fit_figure_to_map(fig, ax, cbar, title, fig_width, fig_height)
    # what savefig would do
    fig.canvas.draw()
    return fig, ax, cbar, gl


def _empty_room(fig, ax):
    """The width and height of the room around the map that it does not
    fill, in inches"""
    width, height = fig.get_size_inches()
    cell = ax.get_position(original=True)
    box = ax.get_position(original=False)
    empty_width = (cell.width - box.width) * width
    empty_height = (cell.height - box.height) * height
    return empty_width, empty_height


def _cropped_text(fig, ax, cbar, gl):
    """The gridline labels, colorbar text and title not wholly inside the
    figure"""
    renderer = fig.canvas.get_renderer()
    artists = [artist for artist in gl.label_artists if artist.get_visible()]
    artists.extend(cbar.ax.get_yticklabels())
    artists.append(cbar.ax.yaxis.label)
    if fig._suptitle is not None:
        artists.append(fig._suptitle)
    cropped = []
    for artist in artists:
        extent = artist.get_window_extent(renderer=renderer)
        if not fig.bbox.contains(extent.x0, extent.y0) or not (
            fig.bbox.contains(extent.x1, extent.y1)
        ):
            cropped.append(artist.get_text())
    return cropped


@pytest.mark.parametrize('projection_name, extent', PROJECTIONS)
@pytest.mark.parametrize('title', [None, 'a title'])
def test_the_map_fills_a_figure_of_a_given_width(
    projection_name, extent, title
):
    with mplstyle_context():
        fig, ax, cbar, gl = _figure(
            projection_name, extent, title, fig_width=8.0, fig_height=None
        )
        assert fig.get_size_inches()[0] == 8.0
        empty_width, empty_height = _empty_room(fig, ax)
        assert empty_height < EMPTY
        assert empty_width < EMPTY
        assert _cropped_text(fig, ax, cbar, gl) == []


@pytest.mark.parametrize('projection_name, extent', PROJECTIONS)
@pytest.mark.parametrize('title', [None, 'a title'])
def test_the_map_fills_a_figure_of_a_given_height(
    projection_name, extent, title
):
    with mplstyle_context():
        fig, ax, cbar, gl = _figure(
            projection_name, extent, title, fig_width=None, fig_height=4.0
        )
        assert fig.get_size_inches()[1] == 4.0
        empty_width, empty_height = _empty_room(fig, ax)
        assert empty_width < EMPTY
        assert empty_height < EMPTY
        assert _cropped_text(fig, ax, cbar, gl) == []


def test_the_figure_is_taller_for_a_taller_map():
    """The point of sizing the figure: a map of a different shape gets a
    figure of a different shape rather than empty canvas"""
    with mplstyle_context():
        fig_global, _, _, _ = _figure(
            'PlateCarree', None, None, fig_width=8.0, fig_height=None
        )
        fig_polar, _, _, _ = _figure(
            'NorthPolarStereo',
            (-180.0, 180.0, 60.0, 90.0),
            None,
            fig_width=8.0,
            fig_height=None,
        )
        assert (
            fig_polar.get_size_inches()[1]
            > 1.5 * (fig_global.get_size_inches()[1])
        )


def test_giving_both_dimensions_is_an_error():
    config = PolarisConfigParser()
    with pytest.raises(ValueError, match='not both'):
        plot_global_mpas_field(
            da=None,
            out_filename='unused.png',
            config=config,
            colormap_section='viz',
            fig_width=8.0,
            fig_height=4.0,
        )


def test_the_plot_is_written_at_the_given_width(tmp_path):
    """The whole function, on a small mesh, without the land features that
    would have to be downloaded"""
    mesh_ds = _quad_mesh_dataset(4, 4)
    mesh_filename = str(tmp_path / 'mesh.nc')
    mesh_ds.to_netcdf(mesh_filename)
    da = mesh_ds.latCell
    config = PolarisConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', 'mpas-ocean')
    config.add_section('viz')
    config.set('viz', 'colormap_name', 'viridis')
    config.set('viz', 'norm_type', 'linear')
    config.set('viz', 'norm_args', '{"vmin": 0.0, "vmax": 0.1}')
    out_filename = str(tmp_path / 'plot.png')

    descriptor = plot_global_mpas_field(
        da,
        out_filename,
        config,
        'viz',
        mesh_filename=mesh_filename,
        title='a title',
        plot_land=False,
        dpi=100,
        fig_width=6.0,
        extent=(-180.0, 180.0, -90.0, 90.0),
    )

    with Image.open(out_filename) as image:
        assert image.size[0] == 600
        # a PlateCarree map of the globe is twice as wide as it is tall, so
        # the figure is a good deal shorter than it is wide
        assert image.size[1] < 400
    # the descriptor is returned so that it can be reused
    assert descriptor is not None
