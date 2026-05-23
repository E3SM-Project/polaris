import json
import os

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from shapely.geometry import box

from polaris.step import Step
from polaris.viz import plot_global_lat_lon_field, plot_global_mpas_field

CONUS_EXTENT = (-128.0, -65.0, 22.0, 52.0)


class VizBaseMeshStep(Step):
    """
    Visualize the final unified base mesh together with key inputs.

    Produces a resolution map and a dcEdge map on the MPAS mesh, a
    sizing-field map on the lat-lon source grid, and a river-alignment
    figure showing the retained river geometry passed to JIGSAW.  A
    plain-text debug summary with key scalar diagnostics is also written.

    Attributes
    ----------
    base_mesh_step : polaris.Step
        The shared base-mesh build step whose output is visualized.

    sizing_step : polaris.Step
        The shared sizing-field build step whose output is visualized.

    river_clip_step : polaris.Step
        The shared river-base-mesh preparation step whose clipped geometry
        is visualized.

    output_filenames : list of str
        The names of the output files produced by this step.
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        sizing_step,
        river_clip_step,
        subdir,
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        base_mesh_step : polaris.Step
            The shared base-mesh build step whose output is visualized.

        sizing_step : polaris.Step
            The shared sizing-field build step whose output is visualized.

        river_clip_step : polaris.Step
            The shared river-base-mesh step whose clipped geometry is
            visualized.

        subdir : str
            The subdirectory within the component's work directory where
            this step will run.
        """
        super().__init__(
            component=component,
            name='base_mesh_viz',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.base_mesh_step = base_mesh_step
        self.sizing_step = sizing_step
        self.river_clip_step = river_clip_step
        self.output_filenames = [
            'base_mesh_resolution.png',
            'base_mesh_dc_edge.png',
            'sizing_field.png',
            'river_alignment.png',
            'debug_summary.txt',
        ]

    def setup(self):
        """
        Link the final mesh, sizing field and retained river geometry.
        """
        self.add_input_file(
            filename='base_mesh.nc',
            work_dir_target=os.path.join(
                self.base_mesh_step.path, 'base_mesh.nc'
            ),
        )
        self.add_input_file(
            filename='sizing_field.nc',
            work_dir_target=os.path.join(
                self.sizing_step.path, self.sizing_step.sizing_field_filename
            ),
        )
        self.add_input_file(
            filename='clipped_river_network.geojson',
            work_dir_target=os.path.join(
                self.river_clip_step.path,
                self.river_clip_step.clipped_filename,
            ),
        )
        for filename in self.output_filenames:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Create durable mesh, sizing-field and river-alignment diagnostics.
        """
        with xr.open_dataset('base_mesh.nc') as ds_mesh:
            area_km2 = ds_mesh.areaCell * 1.0e-6
            resolution_km = _estimate_dc_edge_from_area_cell(area_km2.values)
            dc_edge_km = 1.0e-3 * ds_mesh.dcEdge
            da_resolution = xr.DataArray(
                resolution_km,
                dims=('nCells',),
                coords={'nCells': ds_mesh.nCells},
                name='cell_width_estimate',
            )
            plot_global_mpas_field(
                da=da_resolution,
                mesh_filename='base_mesh.nc',
                out_filename='base_mesh_resolution.png',
                config=self.config,
                colormap_section='viz_base_mesh_resolution',
                title='Unified base mesh cell-width estimate (km)',
                colorbar_label='Estimated cell width (km)',
            )
            plot_global_mpas_field(
                da=dc_edge_km,
                mesh_filename='base_mesh.nc',
                out_filename='base_mesh_dc_edge.png',
                config=self.config,
                colormap_section='viz_base_mesh_resolution',
                title='Unified base mesh dcEdge (km)',
                colorbar_label='dcEdge (km)',
            )
            dc_edge_min = float(dc_edge_km.min().values)
            dc_edge_max = float(dc_edge_km.max().values)

        with xr.open_dataset('sizing_field.nc') as ds_sizing:
            plot_global_lat_lon_field(
                lon=ds_sizing.lon.values,
                lat=ds_sizing.lat.values,
                data_array=ds_sizing.cellWidth.values,
                out_filename='sizing_field.png',
                config=self.config,
                colormap_section='viz_base_mesh_resolution',
                title='Unified sizing field (km)',
                colorbar_label='Cell width (km)',
            )
            sizing_min = float(ds_sizing.cellWidth.min().values)
            sizing_max = float(ds_sizing.cellWidth.max().values)

        river_lines, bounds = _read_river_lines(
            'clipped_river_network.geojson'
        )
        self._plot_river_alignment(river_lines=river_lines, bounds=bounds)

        with open('debug_summary.txt', 'w', encoding='utf-8') as summary:
            summary.write(f'mesh_name: {self.base_mesh_step.mesh_name}\n')
            summary.write(f'nCells: {resolution_km.size}\n')
            summary.write(
                f'base_mesh_cell_width_estimate_min_km: '
                f'{float(np.min(resolution_km)):.6f}\n'
            )
            summary.write(
                f'base_mesh_cell_width_estimate_max_km: '
                f'{float(np.max(resolution_km)):.6f}\n'
            )
            summary.write(f'base_mesh_dc_edge_min_km: {dc_edge_min:.6f}\n')
            summary.write(f'base_mesh_dc_edge_max_km: {dc_edge_max:.6f}\n')
            summary.write(f'sizing_field_min_km: {sizing_min:.6f}\n')
            summary.write(f'sizing_field_max_km: {sizing_max:.6f}\n')
            summary.write(
                'river_alignment_note: river_alignment.png shows the '
                'retained river geometry passed to JIGSAW, not inferred '
                'river cells on the MPAS mesh\n'
            )
            summary.write(
                f'retained_river_bounds: {bounds[0]:.6f}, {bounds[1]:.6f}, '
                f'{bounds[2]:.6f}, {bounds[3]:.6f}\n'
            )
            summary.write(
                f'retained_river_feature_count: {len(river_lines)}\n'
            )

    def _plot_river_alignment(self, river_lines, bounds):
        """
        Plot the retained river geometry passed into final mesh generation.

        Parameters
        ----------
        river_lines : list of numpy.ndarray
            Each element is an (N, 2) array of (longitude, latitude)
            coordinates for one river line segment.

        bounds : tuple of float
            The (west, east, south, north) bounding box of all river lines
            in degrees.
        """
        section = self.config['viz_unified_base_mesh']
        dpi = section.getint('dpi')
        padding = section.getfloat('regional_padding_degrees')

        fig = plt.figure(figsize=(14.0, 7.5), dpi=dpi, constrained_layout=True)
        global_ax = fig.add_subplot(1, 2, 1, projection=ccrs.Robinson())
        global_ax.set_global()
        global_ax.coastlines(linewidth=0.4)
        _plot_river_lines(global_ax, river_lines)
        global_ax.set_title('Retained river geometry passed to JIGSAW')

        regional_ax = fig.add_subplot(1, 2, 2, projection=ccrs.PlateCarree())
        use_example_inset = _use_example_regional_view(bounds)
        extent = _get_regional_extent(bounds=bounds, padding=padding)
        regional_ax.set_extent(extent, crs=ccrs.PlateCarree())
        if use_example_inset:
            regional_title = 'CONUS example view'
            _plot_inset_outline(ax=global_ax, extent=extent)
        else:
            regional_title = 'Regional retained river geometry view'
        regional_ax.coastlines(linewidth=0.4)
        _plot_river_lines(regional_ax, river_lines)
        regional_ax.set_title(regional_title)

        fig.savefig('river_alignment.png', bbox_inches='tight')
        plt.close(fig)


def _estimate_dc_edge_from_area_cell(area_km2):
    """
    Estimate ``dcEdge`` from ``areaCell`` using a regular hexagon.

    For a regular Voronoi hex cell, ``areaCell = sqrt(3) / 2 * dcEdge**2``.
    Solving for ``dcEdge`` gives the estimate below.

    Parameters
    ----------
    area_km2 : numpy.ndarray
        Cell areas in km².

    Returns
    -------
    dc_edge_km : numpy.ndarray
        Estimated cell widths in km, one per cell.
    """
    return np.sqrt(2.0 * area_km2 / np.sqrt(3.0))


def _read_river_lines(filename):
    """
    Read retained river lines and their lon/lat bounds from GeoJSON.

    Parameters
    ----------
    filename : str
        Path to a GeoJSON file containing LineString or MultiLineString
        features.

    Returns
    -------
    river_lines : list of numpy.ndarray
        Each element is an (N, 2) float64 array of (longitude, latitude)
        coordinates for one line segment with at least two points.

    bounds : tuple of float
        The (west, east, south, north) bounding box in degrees covering all
        returned line segments, or ``(-180, 180, -90, 90)`` when the file
        contains no valid line segments.
    """
    with open(filename, encoding='utf-8') as handle:
        feature_collection = json.load(handle)

    river_lines = []
    bounds = [180.0, -180.0, 90.0, -90.0]
    for feature in feature_collection.get('features', []):
        geometry = feature.get('geometry')
        for coords in _iter_line_coordinates(geometry):
            river_lines.append(coords)
            bounds[0] = min(bounds[0], float(np.min(coords[:, 0])))
            bounds[1] = max(bounds[1], float(np.max(coords[:, 0])))
            bounds[2] = min(bounds[2], float(np.min(coords[:, 1])))
            bounds[3] = max(bounds[3], float(np.max(coords[:, 1])))

    if len(river_lines) == 0:
        bounds = [-180.0, 180.0, -90.0, 90.0]

    return river_lines, tuple(bounds)


def _iter_line_coordinates(geometry):
    """
    Yield line coordinates from GeoJSON line-like geometries.

    Handles ``LineString``, ``MultiLineString``, and ``GeometryCollection``
    types.  Only segments with at least two points are yielded.

    Parameters
    ----------
    geometry : dict or None
        A GeoJSON geometry object.

    Yields
    ------
    coords : numpy.ndarray
        An (N, 2) float64 array of (longitude, latitude) pairs for one
        line segment with N >= 2 points.
    """
    if geometry is None:
        return

    geometry_type = geometry.get('type')
    if geometry_type == 'LineString':
        coords = np.asarray(geometry['coordinates'], dtype=np.float64)
        if coords.shape[0] >= 2:
            yield coords
    elif geometry_type == 'MultiLineString':
        for coordinates in geometry['coordinates']:
            coords = np.asarray(coordinates, dtype=np.float64)
            if coords.shape[0] >= 2:
                yield coords
    elif geometry_type == 'GeometryCollection':
        for sub_geometry in geometry.get('geometries', []):
            yield from _iter_line_coordinates(sub_geometry)


def _plot_river_lines(ax, river_lines):
    """
    Plot retained river lines on a Cartopy axis.

    Parameters
    ----------
    ax : cartopy.mpl.geoaxes.GeoAxes
        The axis on which to draw the river lines.

    river_lines : list of numpy.ndarray
        Each element is an (N, 2) array of (longitude, latitude) coordinates.
    """
    for coords in river_lines:
        ax.plot(
            coords[:, 0],
            coords[:, 1],
            color='#0a6ba8',
            linewidth=0.45,
            alpha=0.7,
            transform=ccrs.PlateCarree(),
        )


def _plot_inset_outline(ax, extent):
    """
    Highlight the example inset region on the global map.

    Parameters
    ----------
    ax : cartopy.mpl.geoaxes.GeoAxes
        The global-view axis on which to draw the outline box.

    extent : tuple of float
        The (west, east, south, north) extent in degrees of the inset region.
    """
    ax.add_geometries(
        [box(extent[0], extent[2], extent[1], extent[3])],
        crs=ccrs.PlateCarree(),
        facecolor='none',
        edgecolor='#4a5568',
        linewidth=1.0,
        linestyle='--',
        zorder=6,
    )


def _use_example_regional_view(bounds):
    """
    Decide whether to fall back to a fixed example regional view.

    A fixed CONUS example view is used when the retained river geometry
    spans more than 120° of longitude or 70° of latitude, which would
    make a zoomed regional view unhelpful.

    Parameters
    ----------
    bounds : tuple of float
        The (west, east, south, north) bounding box in degrees.

    Returns
    -------
    use_example : bool
        ``True`` if the example inset should be used instead of a
        geometry-derived regional view.
    """
    west, east, south, north = bounds
    return east - west > 120.0 or north - south > 70.0


def _get_regional_extent(bounds, padding):
    """
    Get a readable regional extent from river bounds.

    Falls back to :data:`CONUS_EXTENT` when the bounds span too large an
    area (see :func:`_use_example_regional_view`).

    Parameters
    ----------
    bounds : tuple of float
        The (west, east, south, north) bounding box in degrees.

    padding : float
        Degrees of padding to add around the bounds on each side.

    Returns
    -------
    extent : tuple of float
        The (west, east, south, north) extent in degrees, clamped to
        ±180° longitude and ±90° latitude.
    """
    west, east, south, north = bounds
    if _use_example_regional_view(bounds):
        return CONUS_EXTENT

    return (
        max(-180.0, west - padding),
        min(180.0, east + padding),
        max(-90.0, south - padding),
        min(90.0, north + padding),
    )
