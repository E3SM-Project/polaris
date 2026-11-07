"""
The protocol's ocean fields on its 2 km by 5 m output grid (Asay-Davis et
al. 2016, Sect. 3.3), written on request
"""

import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.ocean import compute_barotropic_streamfunction
from scipy.sparse import csr_matrix

from polaris import Step
from polaris.mpas.time_series_stats import rename_time_series_stats
from polaris.ocean.ice_shelf.diagnostics import (
    compute_haline_driving,
    compute_melt_rate,
    compute_thermal_driving,
)
from polaris.ocean.overturning import (
    compute_line_interfaces,
    compute_line_transport,
    compute_overturning_in_z,
    get_line_edges,
    interp_overturning_to_z,
)
from polaris.remap import MappingFileStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    TIME_SERIES_FILENAME,
    add_geometry_inputs,
    compute_budget_overturning,
    isomip_mesh,
    read_initial_condition,
    read_layer_thickness_snapshots,
)
from polaris.tasks.e3sm.init.misomip.projection import get_lat_lon
from polaris.tasks.e3sm.init.misomip.scrip import write_scrip

#: The protocol's output grid: cell centers (m)
PROTOCOL_X = 321.0e3 + 2.0e3 * np.arange(240)
PROTOCOL_Y = 1.0e3 + 2.0e3 * np.arange(40)
PROTOCOL_Z = -2.5 - 5.0 * np.arange(144)

#: The spacing (m) of the output grid
PROTOCOL_DX = 2.0e3
PROTOCOL_DZ = 5.0

#: The map from the ocean's mesh to the protocol's grid
MAP_FILENAME = 'map.nc'

#: Days in each month of the 365-day calendar
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class ProtocolMapStep(MappingFileStep):
    """
    A step that makes the conservative map from a run's ocean mesh to the
    protocol's output grid, with SCRIP files of both from the MISOMIP
    meshes' projection
    """

    def __init__(self, component, subdir, diagnostics):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        diagnostics : RunDiagnostics
            The diagnostics step of the run, whose mesh is mapped
        """
        super().__init__(
            component=component,
            name=subdir.replace('/', '_'),
            subdir=subdir,
            ntasks=4,
            min_tasks=1,
            map_filename=MAP_FILENAME,
            method='conserve',
        )
        add_geometry_inputs(self, diagnostics)
        self.add_output_file(filename=MAP_FILENAME)

    def runtime_setup(self):
        """
        Write the SCRIP files, then set up the mapping tool
        """
        ds_mesh = isomip_mesh(read_initial_condition())
        write_scrip(ds_mesh, 'ocean_scrip.nc')
        write_protocol_scrip('protocol_scrip.nc')
        self.src_from_scrip('ocean_scrip.nc', mesh_name='ocean')
        self.dst_from_scrip('protocol_scrip.nc', mesh_name='protocol')
        super().runtime_setup()


class ProtocolFields(Step):
    """
    A step that writes the protocol's ocean fields for one run, on its
    output grid, as monthly means

    Attributes
    ----------
    experiment : str
        The experiment, such as ``ocean0``

    kind : str
        The kind of run, which names the file

    monthly_filenames : list of str
        The local names of the run's monthly means
    """

    def __init__(self, component, subdir, diagnostics, map_step, kind):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        diagnostics : RunDiagnostics
            The diagnostics step of the run

        map_step : ProtocolMapStep
            The step with the map to the protocol's grid

        kind : str
            The kind of run
        """
        super().__init__(
            component=component,
            name=subdir.replace('/', '_'),
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.experiment = diagnostics.experiment
        self.kind = kind
        add_geometry_inputs(self, diagnostics)
        self.add_input_file(
            filename=MAP_FILENAME,
            work_dir_target=f'{map_step.path}/{MAP_FILENAME}',
        )
        self.add_input_file(
            filename=TIME_SERIES_FILENAME,
            work_dir_target=f'{diagnostics.path}/{TIME_SERIES_FILENAME}',
        )
        self.monthly_filenames = list(diagnostics.monthly_filenames)
        self.snapshot_filenames = list(diagnostics.snapshot_filenames)
        for filename in self.monthly_filenames + self.snapshot_filenames:
            self.add_input_file(
                filename=filename,
                work_dir_target=f'{diagnostics.path}/{filename}',
            )
        self.ref_density = diagnostics.ref_density
        self.starts_from_initial_condition = (
            diagnostics.starts_from_initial_condition
        )
        self.add_dependency(diagnostics)
        self.add_dependency(map_step)
        self.add_output_file(filename=self.output_filename)

    def _overturning(self, ds_mesh, ds_init, ds):
        """The overturning streamfunction (m3 s-1) on the protocol's grid:
        from the volume budget, interpolated in z from the mean elevations
        of the layer interfaces along each line, in the months the run has
        its inputs, and from the monthly means of velocity and thickness
        otherwise"""
        result = _overturning(ds_mesh, ds)
        if not self.snapshot_filenames:
            return result
        restoring_x = self.config.getfloat('misomip_analysis', 'restoring_x')
        x_lines = PROTOCOL_X[PROTOCOL_X <= restoring_x]
        ds_osf = compute_budget_overturning(
            ds,
            ds_init,
            read_layer_thickness_snapshots(self.snapshot_filenames),
            x_lines,
            self.ref_density,
            initial_day=0.0 if self.starts_from_initial_condition else None,
        )
        if ds_osf is None:
            return result
        values = result.filled(np.nan)
        for t_index in range(ds_osf.sizes['Time']):
            budget = ds_osf.overturningBudget.isel(Time=t_index)
            if not np.any(np.isfinite(budget.values)):
                continue
            in_z = interp_overturning_to_z(
                budget,
                ds_osf.interfaceElevation.isel(Time=t_index),
                PROTOCOL_Z,
            ).transpose('nZInterfaces', 'x')
            values[t_index] = np.nan
            values[t_index, :, : len(x_lines)] = 1e6 * in_z.values
        return np.ma.masked_invalid(values)

    @property
    def output_filename(self):
        """The file, named as the protocol names them"""
        experiment = self.experiment.capitalize()
        return f'{experiment}_TYP_Polaris-{self.kind}.nc'

    def run(self):
        """
        Write the protocol's fields
        """
        ds_init = read_initial_condition()
        ds_mesh = isomip_mesh(ds_init)
        ds = rename_time_series_stats(
            xr.open_mfdataset(
                self.monthly_filenames,
                combine='nested',
                concat_dim='Time',
                decode_times=False,
                data_vars='minimal',
            )
        ).load()
        ds_series = xr.open_dataset(TIME_SERIES_FILENAME)
        mapping = _read_map(MAP_FILENAME)
        count = ds.sizes['Time']

        floating = ds_init.landIceFloatingFraction
        if 'landIceFloatingFraction' in ds:
            floating = ds.landIceFloatingFraction
        ocean = xr.ones_like(ds_init.areaCell)

        fields = dict()
        # the flux is a mean over each cell, so the ice base melts at the
        # flux over the floating fraction
        fields['meltRate'] = (
            compute_melt_rate(ds.landIceFreshwaterFlux)
            / floating.where(floating > 0.0)
        ).fillna(0.0)
        fields['frictionVelocity'] = ds.landIceFrictionVelocity
        fields['thermalDriving'] = compute_thermal_driving(ds)
        fields['halineDriving'] = compute_haline_driving(ds)
        top = ds_init.minLevelCell - 1
        bottom = ds_init.maxLevelCell - 1
        fields['uBoundaryLayer'] = ds.velocityZonal.isel(nVertLevels=top)
        fields['vBoundaryLayer'] = ds.velocityMeridional.isel(nVertLevels=top)
        under_ice = list(fields)
        fields['bottomTemperature'] = ds.temperature.isel(nVertLevels=bottom)
        fields['bottomSalinity'] = ds.salinity.isel(nVertLevels=bottom)

        out = netCDF4.Dataset(self.output_filename, 'w', format='NETCDF4')
        _define_grid(out, count)
        out.variables['time'][:] = _start_seconds(ds)
        for name, values in [
            ('meanMeltRate', ds_series.meanMeltRate.values),
            ('totalMeltFlux', ds_series.totalMeltFlux.values),
            ('totalOceanVolume', ds_series.oceanVolume.values),
            ('meanTemperature', ds_series.meanTemperature.values),
            ('meanSalinity', ds_series.meanSalinity.values),
        ]:
            out.variables[name][:] = values
        draft = ds_init.landIceDraft
        if 'landIceDraftForSsh' in ds:
            draft = ds.landIceDraftForSsh
        for t_index in range(count):
            for name, field in fields.items():
                weights = floating if name in under_ice else ocean
                if 'Time' in weights.dims:
                    weights = weights.isel(Time=t_index)
                out.variables[name][t_index] = _remap(
                    mapping, field.isel(Time=t_index).values, weights.values
                )
            month_draft = draft
            if 'Time' in draft.dims:
                month_draft = draft.isel(Time=t_index)
            out.variables['iceDraft'][t_index] = _remap(
                mapping, month_draft.values, ocean.values
            )
            out.variables['bathymetry'][t_index] = _remap(
                mapping, -ds_init.bottomDepth.values, ocean.values
            )
        bsf = _barotropic_streamfunction(ds_init, ds)
        for t_index in range(count):
            out.variables['barotropicStreamfunction'][t_index] = _remap(
                mapping, bsf[t_index], ocean.values
            )
        out.variables['overturningStreamfunction'][:] = self._overturning(
            ds_mesh, ds_init, ds
        )
        for axis, name_suffix in [('x', 'XZ'), ('y', 'YZ')]:
            sections = _sections(ds_mesh, ds_init, ds, axis)
            for tracer in ['temperature', 'salinity']:
                out.variables[f'{tracer}{name_suffix}'][:] = sections[tracer]
        out.close()


def write_protocol_scrip(filename):
    """
    Write a SCRIP file of the protocol's 2 km output grid, with the MISOMIP
    meshes' latitude and longitude

    Parameters
    ----------
    filename : str
        The SCRIP file to write
    """
    x_center, y_center = np.meshgrid(PROTOCOL_X, PROTOCOL_Y)
    half = 0.5 * PROTOCOL_DX
    offsets = [(-half, -half), (half, -half), (half, half), (-half, half)]
    x_corner = np.stack([x_center + dx for dx, _ in offsets], axis=-1)
    y_corner = np.stack([y_center + dy for _, dy in offsets], axis=-1)
    lat_center, lon_center = get_lat_lon(x_center.ravel(), y_center.ravel())
    lat_corner, lon_corner = get_lat_lon(x_corner.ravel(), y_corner.ravel())
    count = x_center.size
    ds = xr.Dataset()
    ds['grid_dims'] = (
        'grid_rank',
        np.array([len(PROTOCOL_X), len(PROTOCOL_Y)], dtype=np.int32),
    )
    ds['grid_center_lat'] = ('grid_size', np.rad2deg(lat_center))
    ds['grid_center_lon'] = ('grid_size', np.rad2deg(lon_center))
    ds['grid_corner_lat'] = (
        ('grid_size', 'grid_corners'),
        np.rad2deg(lat_corner).reshape(count, 4),
    )
    ds['grid_corner_lon'] = (
        ('grid_size', 'grid_corners'),
        np.rad2deg(lon_corner).reshape(count, 4),
    )
    ds['grid_imask'] = ('grid_size', np.ones(count, dtype=np.int32))
    for name in ['grid_center_lat', 'grid_center_lon']:
        ds[name].attrs['units'] = 'degrees'
    for name in ['grid_corner_lat', 'grid_corner_lon']:
        ds[name].attrs['units'] = 'degrees'
    write_netcdf(ds, filename)


def bin_column(values, z_top, z_bottom, z_edges):
    """
    Average a column's layer values over bins of elevation by the overlap of
    each layer with each bin

    Parameters
    ----------
    values : numpy.ndarray
        The value in each layer, NaN for invalid layers

    z_top, z_bottom : numpy.ndarray
        The elevations (m) of the top and bottom of each layer

    z_edges : numpy.ndarray
        The edges (m) of the bins, descending

    Returns
    -------
    binned : numpy.ndarray
        The mean in each bin, NaN where no water overlaps the bin
    """
    upper = np.minimum(z_top[:, np.newaxis], z_edges[np.newaxis, :-1])
    lower = np.maximum(z_bottom[:, np.newaxis], z_edges[np.newaxis, 1:])
    overlap = np.clip(upper - lower, 0.0, None)
    valid = np.isfinite(values)[:, np.newaxis]
    overlap = np.where(valid, overlap, 0.0)
    weight = overlap.sum(axis=0)
    total = (np.where(valid, values[:, np.newaxis], 0.0) * overlap).sum(axis=0)
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(weight > 0.0, total / weight, np.nan)


def _define_grid(out, count):
    """Define the protocol's dimensions and variables (Sect. 3.3)"""
    out.createDimension('nTime', count)
    out.createDimension('nx', len(PROTOCOL_X))
    out.createDimension('ny', len(PROTOCOL_Y))
    out.createDimension('nz', len(PROTOCOL_Z))
    for name, dims, values in [
        ('x', ('nx',), PROTOCOL_X),
        ('y', ('ny',), PROTOCOL_Y),
        ('z', ('nz',), PROTOCOL_Z),
    ]:
        var = out.createVariable(name, 'f4', dims)
        var[:] = values
        var.units = 'm'
    out.createVariable('time', 'f4', ('nTime',)).units = 's'
    specs: list[tuple[str, tuple[str, ...], str]] = [
        ('meanMeltRate', ('nTime',), 'm s-1'),
        ('totalMeltFlux', ('nTime',), 'kg s-1'),
        ('totalOceanVolume', ('nTime',), 'm3'),
        ('meanTemperature', ('nTime',), 'degC'),
        ('meanSalinity', ('nTime',), 'PSU'),
    ]
    for name, units in [
        ('iceDraft', 'm'),
        ('bathymetry', 'm'),
        ('meltRate', 'm s-1'),
        ('frictionVelocity', 'm s-1'),
        ('thermalDriving', 'degC'),
        ('halineDriving', 'PSU'),
        ('uBoundaryLayer', 'm s-1'),
        ('vBoundaryLayer', 'm s-1'),
        ('barotropicStreamfunction', 'm3 s-1'),
        ('bottomTemperature', 'degC'),
        ('bottomSalinity', 'PSU'),
    ]:
        specs.append((name, ('nTime', 'ny', 'nx'), units))
    specs.append(
        ('overturningStreamfunction', ('nTime', 'nz', 'nx'), 'm3 s-1')
    )
    for tracer, units in [('temperature', 'degC'), ('salinity', 'PSU')]:
        specs.append((f'{tracer}XZ', ('nTime', 'nz', 'nx'), units))
        specs.append((f'{tracer}YZ', ('nTime', 'nz', 'ny'), units))
    for name, var_dims, units in specs:
        var = out.createVariable(
            name, 'f4', var_dims, fill_value=netCDF4.default_fillvals['f4']
        )
        var.units = units


def _read_map(filename):
    """Read a mapping file's weights as a sparse matrix"""
    ds = xr.open_dataset(filename)
    return csr_matrix(
        (ds.S.values, (ds.row.values - 1, ds.col.values - 1)),
        shape=(ds.sizes['n_b'], ds.sizes['n_a']),
    )


def _remap(mapping, values, weights):
    """
    Remap a field conservatively, normalized by the remapped weights so a
    field defined only under ice is not diluted
    """
    values = np.where(np.isfinite(values), values, 0.0)
    numerator = mapping @ (values * weights)
    denominator = mapping @ weights
    with np.errstate(invalid='ignore', divide='ignore'):
        result = np.where(denominator > 1e-3, numerator / denominator, np.nan)
    return np.ma.masked_invalid(
        result.reshape(len(PROTOCOL_Y), len(PROTOCOL_X))
    )


def _start_seconds(ds):
    """The start of each month, in seconds since the start of the run"""
    seconds = []
    first = None
    for t_index in range(ds.sizes['Time']):
        xtime = ds.xtime_startMonthly.isel(Time=t_index).values.item()
        if isinstance(xtime, bytes):
            xtime = xtime.decode()
        year, month = int(xtime[:4]), int(xtime[5:7])
        days = 365 * (year - 1) + sum(DAYS_IN_MONTH[: month - 1])
        if first is None:
            first = days
        seconds.append(86400.0 * (days - first))
    return np.array(seconds)


def _barotropic_streamfunction(ds_init, ds):
    """The barotropic streamfunction (m3 s-1) on cells, in each month"""
    vertices = ds_init.verticesOnCell - 1
    valid = vertices >= 0
    result = []
    for t_index in range(ds.sizes['Time']):
        bsf = compute_barotropic_streamfunction(
            ds_init, ds.isel(Time=t_index), prefix='', quiet=True
        )
        cell = bsf.isel(nVertices=vertices.where(valid, 0)).where(valid)
        result.append(1e6 * cell.mean(dim='maxEdges').values)
    return result


def _overturning(ds_mesh, ds):
    """The overturning streamfunction (m3 s-1) on the protocol's grid"""
    top = 0.0
    bottom = -PROTOCOL_DZ * len(PROTOCOL_Z)
    count = ds.sizes['Time']
    result = np.full((count, len(PROTOCOL_Z), len(PROTOCOL_X)), np.nan)
    for i_x, x_line in enumerate(PROTOCOL_X):
        line = get_line_edges(ds_mesh, 'x', x_line)
        if line.sizes['nLineEdges'] == 0:
            continue
        transport = compute_line_transport(
            line, ds.normalVelocity, ds.layerThickness
        )
        z_top, z_bottom = compute_line_interfaces(
            line, ds.ssh, ds.layerThickness
        )
        # the grid spans the domain, from z = 0 to its floor at 720 m, which
        # SSH and the layers pass only by a few cm and by round-off, so their
        # transport goes in the top and bottom bins
        z_top = z_top.clip(max=top)
        z_bottom = z_bottom.clip(min=bottom)
        osf = compute_overturning_in_z(
            transport, z_top, z_bottom, PROTOCOL_DZ, top=top, bottom=bottom
        )
        interfaces = osf.values
        result[:, :, i_x] = 0.5 * (interfaces[:, :-1] + interfaces[:, 1:])
    return np.ma.masked_invalid(result)


def _sections(ds_mesh, ds_init, ds, axis):
    """Temperature and salinity along y = 40 km or x = 520 km, binned into
    the protocol's 5 m bins in the nearest cell to each point"""
    if axis == 'x':
        points_x = PROTOCOL_X
        points_y = np.full_like(PROTOCOL_X, 40.0e3)
    else:
        points_y = PROTOCOL_Y
        points_x = np.full_like(PROTOCOL_Y, 520.0e3)
    x_cell = ds_mesh.xCell.values
    y_cell = ds_mesh.yCell.values
    cells = np.array(
        [
            np.argmin((x_cell - x) ** 2 + (y_cell - y) ** 2)
            for x, y in zip(points_x, points_y, strict=True)
        ]
    )
    z_edges = -PROTOCOL_DZ * np.arange(len(PROTOCOL_Z) + 1)
    count = ds.sizes['Time']
    sections = {
        tracer: np.full((count, len(PROTOCOL_Z), len(cells)), np.nan)
        for tracer in ['temperature', 'salinity']
    }
    thickness = ds.layerThickness.values
    ssh = ds.ssh.values
    for t_index in range(count):
        for i_point, cell in enumerate(cells):
            h = np.nan_to_num(thickness[t_index, cell])
            z_bottom = ssh[t_index, cell] - np.cumsum(h)
            z_top = z_bottom + h
            for tracer, values in sections.items():
                column = ds[tracer].values[t_index, cell]
                values[t_index, :, i_point] = bin_column(
                    np.where(h > 0.0, column, np.nan), z_top, z_bottom, z_edges
                )
    return {
        tracer: np.ma.masked_invalid(values)
        for tracer, values in sections.items()
    }
