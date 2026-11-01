import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.ocean import compute_barotropic_streamfunction

from polaris import Step
from polaris.mpas.time_series_stats import rename_time_series_stats
from polaris.ocean.ice_shelf.diagnostics import (
    compute_haline_driving,
    compute_melt_diagnostics,
    compute_melt_rate,
    compute_melt_rate_by_draft,
    compute_thermal_driving,
    compute_thin_film_diagnostics,
)
from polaris.ocean.overturning import (
    compute_line_interfaces,
    compute_line_transport,
    compute_overturning_in_z,
    get_line_edges,
)
from polaris.tasks.e3sm.analysis.misomip.runs import (
    DAILY_STREAM,
    get_mean_months,
)

#: The files a diagnostics step writes
TIME_SERIES_FILENAME = 'time_series.nc'
TIME_MEAN_FILENAME = 'time_mean.nc'
MONTHLY_MAPS_FILENAME = 'monthly_maps.nc'
DAILY_FILENAME = 'daily.nc'
INIT_FILENAME = 'init.nc'

#: The fields of the daily global statistics kept for comparisons
DAILY_FIELDS = [
    'landIceFreshwaterFluxTotalSum',
    'volumeCellGlobal',
    'temperatureAvg',
    'salinityAvg',
    'kineticEnergyCellAvg',
]

#: The seconds in a year of 365 days
SECONDS_PER_YEAR = 365.0 * 86400.0


class RunDiagnostics(Step):
    """
    A step that computes the diagnostics of one run of a MISOMIP experiment

    It writes monthly time series, time means over the end of the run,
    monthly maps for comparing runs, and the daily global statistics.

    Attributes
    ----------
    experiment : str
        The experiment, such as ``ocean0``

    monthly_filenames : list of str
        The local names of the monthly means, in order

    daily_filenames : list of str
        The local names of the files of daily global statistics, in order

    min_thickness : float
        The minimum thickness (m) of a layer from the run's namelist, which
        sets which columns are dry
    """

    def __init__(self, component, subdir, configured_run, experiment):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        configured_run : polaris.tasks.e3sm.analysis.misomip.runs.ConfiguredRun
            The run

        experiment : str
            The experiment
        """
        super().__init__(
            component=component,
            name=f'{configured_run.kind}_diagnostics',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.experiment = experiment
        run = configured_run.run
        self.add_input_file(
            filename=INIT_FILENAME, target=run.initial_condition
        )
        self.monthly_filenames = []
        for stream_file in configured_run.monthly:
            filename = os.path.join(
                'monthly', os.path.basename(stream_file.path)
            )
            self.add_input_file(filename=filename, target=stream_file.path)
            self.monthly_filenames.append(filename)
        first = configured_run.monthly[0]
        last = configured_run.monthly[-1]
        self.daily_filenames = []
        for stream_file in run.find_stream_files(DAILY_STREAM):
            if (
                (first.year, first.month)
                <= (
                    stream_file.year,
                    stream_file.month,
                )
                <= (last.year, last.month)
            ):
                filename = os.path.join(
                    'daily', os.path.basename(stream_file.path)
                )
                self.add_input_file(filename=filename, target=stream_file.path)
                self.daily_filenames.append(filename)
        self.min_thickness = _fortran_float(
            run.namelist_option('config_drying_min_cell_height')
        )
        for filename in [
            TIME_SERIES_FILENAME,
            TIME_MEAN_FILENAME,
            MONTHLY_MAPS_FILENAME,
            DAILY_FILENAME,
        ]:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Compute the diagnostics
        """
        config = self.config
        section = config['misomip_analysis']
        ds_init = read_initial_condition(INIT_FILENAME)
        ds = rename_time_series_stats(
            xr.open_mfdataset(
                self.monthly_filenames,
                combine='nested',
                concat_dim='Time',
                decode_times=False,
                data_vars='minimal',
            )
        )
        ds = ds.load()
        ds = _add_bottom_values(ds, ds_init)
        geometry = _geometry(ds, ds_init)

        ds_series = _time_series(
            ds,
            ds_init,
            geometry,
            deep_draft=section.getfloat('deep_draft'),
            min_thickness=self.min_thickness,
        )
        self.logger.info('computing streamfunctions for each month')
        strengths = _streamfunction_strengths(
            ds,
            ds_init,
            geometry,
            dx=section.getfloat('overturning_dx'),
            dz=section.getfloat('overturning_dz'),
        )
        ds_series = xr.merge([ds_series, strengths])
        ds_series = _add_time(ds_series, ds)
        write_netcdf(ds_series, TIME_SERIES_FILENAME)

        count = min(get_mean_months(config, self.experiment), ds.sizes['Time'])
        ds_end = ds.isel(Time=slice(-count, None))
        ds_mean = _time_mean(
            ds_end,
            ds_init,
            _geometry(ds_end, ds_init),
            draft_bin_width=section.getfloat('draft_bin_width'),
            dx=section.getfloat('overturning_dx'),
            dz=section.getfloat('overturning_dz'),
        )
        ds_mean.attrs['first_month'] = _start_date(ds_end, 0)
        ds_mean.attrs['last_month'] = _start_date(ds_end, -1)
        ds_mean.attrs['month_count'] = count
        write_netcdf(ds_mean, TIME_MEAN_FILENAME)

        ds_maps = _add_time(_monthly_maps(ds), ds)
        write_netcdf(ds_maps, MONTHLY_MAPS_FILENAME)

        write_netcdf(self._daily(), DAILY_FILENAME)

    def _daily(self):
        """Gather the daily global statistics"""
        if not self.daily_filenames:
            return xr.Dataset()
        ds = xr.open_mfdataset(
            self.daily_filenames,
            combine='nested',
            concat_dim='Time',
            decode_times=False,
            data_vars='minimal',
        )
        fields = [field for field in DAILY_FIELDS if field in ds]
        ds_daily = ds[fields + ['daysSinceStartOfSim']].load()
        _, unique = np.unique(ds_daily.daysSinceStartOfSim, return_index=True)
        return ds_daily.isel(Time=unique)


def read_initial_condition(filename):
    """
    Read a run's initial condition, which holds its mesh and initial
    geometry, without a ``Time`` dimension

    Parameters
    ----------
    filename : str
        The initial condition

    Returns
    -------
    ds_init : xarray.Dataset
        The initial condition
    """
    ds_init = xr.open_dataset(filename, decode_times=False)
    if 'Time' in ds_init.dims:
        ds_init = ds_init.isel(Time=0)
    return ds_init


def isomip_mesh(ds_init):
    """
    Get a copy of the mesh whose cell and vertex coordinates are the
    protocol's, for plotting and for lines of constant x

    Parameters
    ----------
    ds_init : xarray.Dataset
        A dataset with the mesh and ``xIsomipCell``, ``yIsomipCell``,
        ``xIsomipVertex`` and ``yIsomipVertex``

    Returns
    -------
    ds_mesh : xarray.Dataset
        The mesh with ``xCell``, ``yCell``, ``xVertex`` and ``yVertex`` in
        the protocol's coordinates, in m
    """
    ds_mesh = ds_init.copy()
    for location in ['Cell', 'Vertex']:
        for coord in ['x', 'y']:
            ds_mesh[f'{coord}{location}'] = ds_init[f'{coord}Isomip{location}']
        ds_mesh[f'z{location}'] = xr.zeros_like(ds_mesh[f'x{location}'])
    ds_mesh.attrs['on_a_sphere'] = 'NO'
    ds_mesh.attrs['is_periodic'] = 'NO'
    return ds_mesh


def _fortran_float(value):
    """Parse a Fortran real, which may use d for its exponent"""
    return float(value.lower().replace('d', 'e'))


def _geometry(ds, ds_init):
    """
    The land-ice geometry: from the monthly means where the geometry moves,
    otherwise from the initial condition
    """
    geometry = dict()
    for name, init_name in [
        ('landIceFraction', 'landIceFraction'),
        ('landIceFloatingFraction', 'landIceFloatingFraction'),
        ('landIceDraftForSsh', 'landIceDraft'),
    ]:
        if name in ds:
            geometry[init_name] = ds[name]
        else:
            geometry[init_name] = ds_init[init_name]
    return geometry


def _add_bottom_values(ds, ds_init):
    """Add the temperature and salinity in each column's bottom layer"""
    bottom = ds_init.maxLevelCell - 1
    for name in ['temperature', 'salinity']:
        ds[f'{name}Bottom'] = ds[name].isel(nVertLevels=bottom)
    return ds


def _time_series(ds, ds_init, geometry, deep_draft, min_thickness):
    """Compute the monthly time series"""
    area = ds_init.areaCell
    ds_series = compute_melt_diagnostics(
        area,
        ds,
        geometry['landIceFloatingFraction'],
        draft=geometry['landIceDraft'],
        deep_draft=deep_draft,
    )
    thickness = ds.layerThickness
    volume = (thickness * area).sum(dim=['nCells', 'nVertLevels'])
    ds_series['oceanVolume'] = volume
    ds_series.oceanVolume.attrs = dict(long_name='ocean volume', units='m3')
    for name, units in [('temperature', 'degC'), ('salinity', 'PSU')]:
        total = (ds[name] * thickness * area).sum(
            dim=['nCells', 'nVertLevels']
        )
        ds_series[f'mean{name.capitalize()}'] = total / volume
        ds_series[f'mean{name.capitalize()}'].attrs = dict(
            long_name=f'mean {name}', units=units
        )
    level_count = ds_init.maxLevelCell - ds_init.minLevelCell + 1
    ds_film = compute_thin_film_diagnostics(
        area,
        ds.ssh,
        ds_init.bottomDepth,
        level_count,
        geometry['landIceFraction'],
        geometry['landIceFloatingFraction'],
        min_thickness,
    )
    return xr.merge([ds_series, ds_film])


def _streamfunction_strengths(ds, ds_init, geometry, dx, dz):
    """
    The range under the ice of the barotropic and overturning
    streamfunctions in each month
    """
    floating = geometry['landIceFloatingFraction'] > 0.0
    bsf_range = []
    osf_range = []
    for t_index in range(ds.sizes['Time']):
        ds_month = ds.isel(Time=slice(t_index, t_index + 1))
        floating_month = floating
        if 'Time' in floating.dims:
            floating_month = floating.isel(Time=t_index)
        bsf_cell = _cell_mean_of_vertices(
            ds_init, _barotropic_streamfunction(ds_init, ds_month.isel(Time=0))
        )
        bsf_range.append(_range_where(bsf_cell, floating_month))
        osf = _overturning(ds_month, ds_init, dx, dz).isel(Time=0)
        under_ice = osf.x <= _ice_front_x(ds_init, floating_month)
        osf_range.append(_range_where(osf, under_ice))
    ds_strength = xr.Dataset()
    ds_strength['barotropicStrength'] = ('Time', np.array(bsf_range))
    ds_strength['overturningStrength'] = ('Time', np.array(osf_range))
    ds_strength.barotropicStrength.attrs = dict(
        long_name='range of the barotropic streamfunction under the ice',
        units='Sv',
    )
    ds_strength.overturningStrength.attrs = dict(
        long_name='range of the overturning streamfunction under the ice',
        units='Sv',
    )
    return ds_strength


def _time_mean(ds, ds_init, geometry, draft_bin_width, dx, dz):
    """Compute the time means of maps and sections over the given months"""
    ds_mean = ds.mean(dim='Time')
    floating_fraction = geometry['landIceFloatingFraction']
    if 'Time' in floating_fraction.dims:
        floating_fraction = floating_fraction.mean(dim='Time')

    ds_out = xr.Dataset()
    ds_out['meltRate'] = compute_melt_rate(ds_mean.landIceFreshwaterFlux)
    ds_out['thermalDriving'] = compute_thermal_driving(ds_mean)
    ds_out['halineDriving'] = compute_haline_driving(ds_mean)
    for name in [
        'landIceFrictionVelocity',
        'ssh',
        'temperatureBottom',
        'salinityBottom',
        'temperature',
        'salinity',
        'layerThickness',
    ]:
        ds_out[name] = ds_mean[name]
    ds_out['landIceFloatingFraction'] = floating_fraction
    ds_out['barotropicStreamfunction'] = _barotropic_streamfunction(
        ds_init, ds_mean
    )
    ds_out['overturningStreamfunction'] = _overturning(
        ds_mean.expand_dims('Time'), ds_init, dx, dz
    ).isel(Time=0)

    draft = geometry['landIceDraft']
    if 'Time' in draft.dims:
        draft = draft.mean(dim='Time')
    ds_bins = compute_melt_rate_by_draft(
        ds_init.areaCell,
        ds_mean.landIceFreshwaterFlux,
        floating_fraction,
        draft,
        bin_width=draft_bin_width,
    )
    ds_out['meltRateByDraft'] = ds_bins.meanMeltRate
    ds_out['floatingAreaByDraft'] = ds_bins.floatingArea
    return ds_out


def _monthly_maps(ds):
    """The fields compared map by map between runs, in each month"""
    ds_maps = xr.Dataset()
    ds_maps['meltRate'] = compute_melt_rate(ds.landIceFreshwaterFlux)
    ds_maps['thermalDriving'] = compute_thermal_driving(ds)
    for name in [
        'landIceFrictionVelocity',
        'ssh',
        'temperatureBottom',
        'salinityBottom',
    ]:
        ds_maps[name] = ds[name]
    return ds_maps.astype('float32')


def _barotropic_streamfunction(ds_init, ds_month):
    """The barotropic streamfunction (Sv) on vertices, zero on the outer
    boundary"""
    return compute_barotropic_streamfunction(
        ds_init, ds_month, prefix='', quiet=True
    ).rename('barotropicStreamfunction')


def _cell_mean_of_vertices(ds_init, field_vertex):
    """Average a field on vertices to the cells"""
    vertices = ds_init.verticesOnCell - 1
    valid = vertices >= 0
    values = field_vertex.isel(nVertices=vertices.where(valid, 0))
    return values.where(valid).mean(dim='maxEdges')


def _overturning(ds, ds_init, dx, dz):
    """
    The overturning streamfunction (Sv) across lines of constant x, in the
    protocol's coordinates, on bins of elevation shared by every line
    """
    ds_mesh = isomip_mesh(ds_init)
    x_min = float(ds_mesh.xCell.min())
    x_max = float(ds_mesh.xCell.max())
    x_lines = dx * np.arange(np.floor(x_min / dx) + 1, np.ceil(x_max / dx))
    top = dz * np.ceil(max(float(ds.ssh.max()), 0.0) / dz)
    bottom = -dz * np.ceil(float(ds_init.bottomDepth.max()) / dz)

    columns = []
    for x_line in x_lines:
        line = get_line_edges(ds_mesh, 'x', x_line)
        if line.sizes['nLineEdges'] == 0:
            continue
        transport = compute_line_transport(
            line, ds.normalVelocity, ds.layerThickness
        )
        z_top, z_bottom = compute_line_interfaces(
            line, ds.ssh, ds.layerThickness
        )
        osf = compute_overturning_in_z(
            transport, z_top, z_bottom, dz, top=top, bottom=bottom
        )
        # elevations above the water or below it on this line are not ocean
        wet = z_top > z_bottom
        water_top = z_top.where(wet).max(dim=['nLineEdges', 'nVertLevels'])
        water_bottom = z_bottom.where(wet).min(
            dim=['nLineEdges', 'nVertLevels']
        )
        in_water = np.logical_and(
            osf.zInterface <= water_top + dz,
            osf.zInterface >= water_bottom - dz,
        )
        osf = osf.where(in_water)
        columns.append(osf.expand_dims(x=[1e-3 * x_line]))
    overturning = 1e-6 * xr.concat(columns, dim='x')
    overturning = overturning.transpose('Time', 'nZInterfaces', 'x')
    overturning.attrs = dict(
        long_name='overturning streamfunction', units='Sv'
    )
    overturning.x.attrs = dict(long_name='x', units='km')
    overturning.zInterface.attrs = dict(long_name='elevation', units='m')
    return overturning.rename('overturningStreamfunction')


def _ice_front_x(ds_init, floating):
    """The largest x (km) of any floating cell"""
    x_cell = 1e-3 * ds_init.xIsomipCell
    return float(x_cell.where(floating).max())


def _range_where(field, mask):
    """The range of a field where a mask is true"""
    values = field.where(mask)
    return float(values.max() - values.min())


def _start_date(ds, t_index):
    """The start of a month of monthly means, as YYYY-MM"""
    xtime = ds.xtime_startMonthly.isel(Time=t_index).values.item()
    if isinstance(xtime, bytes):
        xtime = xtime.decode()
    return xtime.strip()[:7]


def _add_time(ds_out, ds):
    """Add the middle of each month, in years since the start of year 1"""
    years = []
    for t_index in range(ds.sizes['Time']):
        date = _start_date(ds, t_index)
        year, month = int(date[:4]), int(date[5:7])
        years.append(year - 1 + (month - 0.5) / 12.0)
    ds_out = ds_out.assign_coords(time=('Time', np.array(years)))
    ds_out.time.attrs = dict(
        long_name='time since the start of year 1', units='years'
    )
    return ds_out
