import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.ocean import compute_barotropic_streamfunction

from polaris import Step
from polaris.constants import get_constant
from polaris.e3sm.analysis.calendar import month_start_days, xtime_to_days
from polaris.e3sm.analysis.runs import E3smRun
from polaris.landice.diagnostics import (
    compute_volume_and_area,
    grounding_line_on_row,
    grounding_line_points,
    thickness_above_flotation,
)
from polaris.mpas.time_series_stats import rename_time_series_stats
from polaris.ocean.ice_shelf.diagnostics import (
    compute_flux_sent_to_land_ice,
    compute_grounding_line_band_diagnostics,
    compute_haline_driving,
    compute_melt_diagnostics,
    compute_melt_rate,
    compute_melt_rate_by_draft,
    compute_open_ocean_ssh_diagnostics,
    compute_thermal_driving,
    compute_thin_film_diagnostics,
    compute_wet_time_mean,
    get_film_columns,
    get_open_ocean_mask,
)
from polaris.ocean.overturning import (
    compute_line_interfaces,
    compute_line_transport,
    compute_overturning_from_edge_transport,
    get_line_edges,
)
from polaris.tasks.e3sm.analysis.misomip.runs import (
    DAILY_MEANS_STREAM,
    DAILY_STREAM,
    SNAPSHOT_STREAM,
    get_mean_months,
)

#: The files a diagnostics step writes
TIME_SERIES_FILENAME = 'time_series.nc'
TIME_MEAN_FILENAME = 'time_mean.nc'
MONTHLY_MAPS_FILENAME = 'monthly_maps.nc'
DAILY_FILENAME = 'daily.nc'
DAILY_EXCHANGE_FILENAME = 'daily_exchange.nc'
DAILY_VOLUME_FILENAME = 'daily_volume.nc'
MONTHLY_VOLUME_FILENAME = 'monthly_volume.nc'
TIDAL_MASK_FILENAME = 'tidal_forcing_mask.nc'
INIT_FILENAME = 'init.nc'
MESH_FILENAME = 'mesh.nc'
LANDICE_FILENAME = 'landice.nc'
LANDICE_INIT_FILENAME = 'landice_init.nc'

#: MALI's history stream
LANDICE_STREAM = 'output'

#: The fields of the ocean's state whose means over several months take
#: only the months each column is wet, each with the field that weights
#: them, or ``None`` to weight the months equally.  Fluxes, such as melt and
#: the transports, keep their means over all months.
WET_MEAN_WEIGHTS = {
    'temperature': 'layerThickness',
    'salinity': 'layerThickness',
    'velocityZonal': 'layerThickness',
    'velocityMeridional': 'layerThickness',
    'temperatureBottom': 'layerThicknessBottom',
    'salinityBottom': 'layerThicknessBottom',
    'layerThickness': None,
    'layerThicknessBottom': None,
    'ssh': None,
    'landIceBoundaryLayerTemperature': None,
    'landIceBoundaryLayerSalinity': None,
    'landIceInterfaceTemperature': None,
    'landIceInterfaceSalinity': None,
    'landIceFrictionVelocity': None,
    'thermalDriving': None,
    'halineDriving': None,
}

#: The fields of the daily global statistics kept for comparisons
DAILY_FIELDS = [
    'landIceFreshwaterFluxTotalSum',
    'volumeCellGlobal',
    'temperatureAvg',
    'salinityAvg',
    'kineticEnergyCellAvg',
]

#: The prefix of the fields in the ocean's daily means
DAILY_MEANS_PREFIX = 'timeDaily_avg_'

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

    daily_mean_filenames : list of str
        The local names of the files of the ocean's daily means, in order,
        empty if the run wrote none

    has_daily_volume : bool
        Whether the run wrote both daily global statistics and daily means,
        from which the ocean's daily volume budget is computed

    tidal_forcing_type : str or None
        The run's ``config_tidal_forcing_type`` if it has tidal forcing

    snapshot_filenames : list of str
        The local names of the files of layer thickness at the start of each
        month analyzed and of the month after, empty if the run wrote none

    has_monthly_volume : bool
        Whether the run has tidal forcing and wrote snapshots of layer
        thickness, from which the volume budget of the cells outside the
        tidally forced ones is computed each month

    min_thickness : float
        The minimum thickness (m) of a layer from the run's namelist, which
        sets which columns are dry

    min_floating_fraction : float
        The floating fraction from the land-ice model above which the ocean
        and land-ice model exchange melt, from the run's namelist

    ref_density : float
        The reference density (kg m-3) of the run's hydrostatic balance,
        from its namelist

    landice_filenames : list of str
        The local names of MALI's history files in the years analyzed, empty
        for a run without MALI

    densities : tuple of float
        MALI's ice and ocean densities (kg m-3) from its namelist, for the
        flotation criterion
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
            # unique across experiments and meshes, since the comparison
            # tasks hold the diagnostics of several
            name=subdir.replace('/', '_'),
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.experiment = experiment
        run = configured_run.run
        initial_run = configured_run.initial_run
        self.add_input_file(
            filename=INIT_FILENAME, target=initial_run.initial_condition
        )
        self.add_input_file(
            filename=MESH_FILENAME, target=initial_run.mesh_file
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
        self.daily_filenames = self._add_daily_inputs(
            run.find_stream_files(DAILY_STREAM), 'daily', first, last
        )
        try:
            daily_means = run.find_stream_files(DAILY_MEANS_STREAM)
        except ValueError:
            # the run's streams file has no daily means
            daily_means = []
        self.daily_mean_filenames = self._add_daily_inputs(
            daily_means, 'daily_means', first, last
        )
        if self.daily_mean_filenames:
            self.add_output_file(filename=DAILY_EXCHANGE_FILENAME)
        self.has_daily_volume = bool(
            self.daily_mean_filenames and self.daily_filenames
        )
        self.tidal_forcing_type = None
        if self.has_daily_volume:
            self.add_output_file(filename=DAILY_VOLUME_FILENAME)
            if _has_tidal_forcing(run):
                self.tidal_forcing_type = (
                    run.namelist_option('config_tidal_forcing_type')
                    .strip()
                    .strip('\'"')
                )
        self.snapshot_filenames = self._add_snapshot_inputs(run, first, last)
        self.has_monthly_volume = bool(self.snapshot_filenames)
        if self.has_monthly_volume:
            self.add_input_file(
                filename=TIDAL_MASK_FILENAME,
                target=run.input_filename('tidal_forcing_mask'),
            )
            self.add_output_file(filename=MONTHLY_VOLUME_FILENAME)
        self.min_thickness = _fortran_float(
            run.namelist_option('config_drying_min_cell_height')
        )
        self.min_floating_fraction = _fortran_float(
            run.namelist_option(
                'config_glc_ice_shelf_coupling_min_floating_fraction'
            )
        )
        self.ref_density = _fortran_float(
            run.namelist_option('config_density0')
        )
        for filename in [
            TIME_SERIES_FILENAME,
            TIME_MEAN_FILENAME,
            MONTHLY_MAPS_FILENAME,
            DAILY_FILENAME,
        ]:
            self.add_output_file(filename=filename)
        self.landice_filenames = []
        self.densities = (0.0, 0.0)
        if configured_run.kind == 'e3sm':
            self._add_landice_inputs(configured_run, first.year, last.year)

    def _add_daily_inputs(self, stream_files, subdir, first, last):
        """Link the daily files in the months of the first and last
        monthly means"""
        filenames = []
        for stream_file in stream_files:
            if (
                (first.year, first.month)
                <= (stream_file.year, stream_file.month)
                <= (last.year, last.month)
            ):
                filename = os.path.join(
                    subdir, os.path.basename(stream_file.path)
                )
                self.add_input_file(filename=filename, target=stream_file.path)
                filenames.append(filename)
        return filenames

    def _add_snapshot_inputs(self, run, first, last):
        """Link the snapshots of layer thickness at the start of each month
        of the monthly means and of the month after, if the run has tidal
        forcing and wrote them"""
        if not _has_tidal_forcing(run):
            return []
        try:
            stream_files = run.find_stream_files(SNAPSHOT_STREAM)
        except ValueError:
            # the run's streams file has no snapshots
            return []
        after = (
            (last.year, last.month + 1)
            if last.month < 12
            else (last.year + 1, 1)
        )
        filenames = []
        for stream_file in stream_files:
            if (
                (first.year, first.month)
                <= (stream_file.year, stream_file.month)
                <= after
            ):
                filename = os.path.join(
                    'snapshots', os.path.basename(stream_file.path)
                )
                self.add_input_file(filename=filename, target=stream_file.path)
                filenames.append(filename)
        return filenames

    def _add_landice_inputs(self, configured_run, start_year, end_year):
        """Link MALI's initial condition and history, if it wrote any"""
        landice = E3smRun(configured_run.path, 'mali')
        streams = os.path.join(landice.case.run_dir, 'streams.landice')
        if not os.path.exists(streams):
            return
        stream_files = [
            stream_file
            for stream_file in landice.find_stream_files(LANDICE_STREAM)
            if start_year <= stream_file.year <= end_year
        ]
        if not stream_files:
            return
        # a run that continues from another reads that run's initial
        # condition, which holds MALI's mesh and bed
        base = configured_run
        while base.continues is not None:
            base = base.continues
        initial = E3smRun(base.path, 'mali')
        self.add_input_file(
            filename=LANDICE_INIT_FILENAME,
            target=initial.initial_condition,
        )
        for stream_file in stream_files:
            filename = os.path.join(
                'landice', os.path.basename(stream_file.path)
            )
            self.add_input_file(filename=filename, target=stream_file.path)
            self.landice_filenames.append(filename)
        self.densities = (
            _fortran_float(landice.namelist_option('config_ice_density')),
            _fortran_float(landice.namelist_option('config_ocean_density')),
        )
        self.add_output_file(filename=LANDICE_FILENAME)

    def run(self):
        """
        Compute the diagnostics
        """
        config = self.config
        section = config['misomip_analysis']
        ds_init = read_initial_condition()
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
        ds = _add_wet_columns(ds, ds_init, geometry, self.min_thickness)

        ds_series = _time_series(
            ds,
            ds_init,
            geometry,
            deep_draft=section.getfloat('deep_draft'),
            min_thickness=self.min_thickness,
            min_floating_fraction=self.min_floating_fraction,
            restoring_x=section.getfloat('restoring_x'),
            ref_density=self.ref_density,
        )
        self.logger.info('computing streamfunctions for each month')
        strengths = _streamfunction_strengths(
            ds,
            ds_init,
            geometry,
            dx=section.getfloat('overturning_dx'),
            dz=section.getfloat('overturning_dz'),
            restoring_x=section.getfloat('restoring_x'),
            bottom_slab=section.getfloat('bottom_slab_thickness'),
        )
        ds_series = xr.merge([ds_series, strengths])
        ds_series['openOceanSshOffset'] = (
            ds_series.openOceanSshResidual
            - ds_series.openOceanBottomGeostrophicSsh
        )
        ds_series.openOceanSshOffset.attrs = dict(
            long_name=(
                "the open ocean's mean residual SSH less the geostrophic "
                'height of its bottom flow'
            ),
            units='m',
        )
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

        if self.daily_mean_filenames:
            write_netcdf(
                self._daily_exchange(ds_init), DAILY_EXCHANGE_FILENAME
            )

        if self.has_daily_volume:
            write_netcdf(
                self._daily_volume(ds_init),
                DAILY_VOLUME_FILENAME,
            )

        if self.has_monthly_volume:
            write_netcdf(
                self._monthly_volume(ds, ds_init), MONTHLY_VOLUME_FILENAME
            )

        if self.landice_filenames:
            section_y = section.getfloat('section_y')
            write_netcdf(self._landice(section_y), LANDICE_FILENAME)

    def _landice(self, section_y):
        """
        Compute the ice sheet's volume, volume above flotation, grounded area
        and grounding line from MALI's thickness and bed
        """
        ds_mesh = xr.open_dataset(LANDICE_INIT_FILENAME, decode_times=False)
        if 'Time' in ds_mesh.dims:
            ds_mesh = ds_mesh.isel(Time=0)
        ds = xr.open_mfdataset(
            self.landice_filenames,
            combine='nested',
            concat_dim='Time',
            decode_times=False,
            data_vars='minimal',
        )
        thickness = ds.thickness.load()
        ice_density, ocean_density = self.densities
        bed = ds_mesh.bedTopography
        ds_landice = compute_volume_and_area(
            thickness, bed, ds_mesh.areaCell, ice_density, ocean_density
        )
        haf = thickness_above_flotation(
            thickness, bed, ice_density, ocean_density
        )
        ds_landice['xGL'] = grounding_line_on_row(haf, ds_mesh, y=section_y)
        ds_landice.xGL.attrs = dict(
            long_name=f'grounding line along y = {section_y:g} m', units='m'
        )
        ds_landice['daysSinceStart'] = ds.daysSinceStart.load()
        ds_landice['daysSince0001'] = (
            'Time',
            xtime_to_days(ds.xtime.values),
        )
        ds_landice.daysSince0001.attrs = dict(
            long_name='time of the record', units='days since 0001-01-01'
        )
        for label, t_index in [('First', 0), ('Last', -1)]:
            x_gl, y_gl = grounding_line_points(haf.isel(Time=t_index), ds_mesh)
            ds_landice[f'xGroundingLine{label}'] = (
                f'nPointsGroundingLine{label}',
                np.asarray(x_gl),
            )
            ds_landice[f'yGroundingLine{label}'] = (
                f'nPointsGroundingLine{label}',
                np.asarray(y_gl),
            )
        return ds_landice

    def _daily_exchange(self, ds_init):
        """
        Compute the ocean's daily melt and the net flux it sends to the
        land-ice model from its daily means
        """
        ds = rename_time_series_stats(
            xr.open_mfdataset(
                self.daily_mean_filenames,
                combine='nested',
                concat_dim='Time',
                decode_times=False,
                data_vars='minimal',
            ),
            prefix=DAILY_MEANS_PREFIX,
        )
        ds_exchange = xr.Dataset()
        # the start is the first sample, which the compute interval puts
        # after the start of the day
        ds_exchange['dayStart'] = (
            'Time',
            np.floor(xtime_to_days(ds.xtime_startDaily.values)),
        )
        ds_exchange['dayEnd'] = (
            'Time',
            xtime_to_days(ds.xtime_endDaily.values),
        )
        for name in ['dayStart', 'dayEnd']:
            ds_exchange[name].attrs = dict(
                long_name=f'{name[3:].lower()} of the day',
                units='days since 0001-01-01',
            )
        if 'landIceFreshwaterFlux' not in ds:
            self.logger.info(
                "The ocean's daily means have no landIceFreshwaterFlux, so "
                'the daily exchange is not computed.'
            )
            return ds_exchange
        fields = [
            name
            for name in [
                'landIceFreshwaterFlux',
                'frazilIceFreshwaterFlux',
                'landIceFreshwaterFluxNotSentToGlc',
                'landIceFraction',
                'landIceGlcFloatingFraction',
            ]
            if name in ds
        ]
        ds = ds[fields].load()
        area = ds_init.areaCell
        ds_exchange['totalMeltFlux'] = (ds.landIceFreshwaterFlux * area).sum(
            dim='nCells'
        )
        ds_exchange.totalMeltFlux.attrs = dict(
            long_name='total melt flux', units='kg s-1'
        )
        if (
            'landIceFreshwaterFluxNotSentToGlc' not in ds
            and 'landIceGlcFloatingFraction' not in ds
        ):
            self.logger.info(
                "The ocean's daily means have neither "
                'landIceFreshwaterFluxNotSentToGlc nor '
                'landIceGlcFloatingFraction, so the daily flux sent to the '
                'land-ice model is not computed.'
            )
            return ds_exchange
        land_ice_fraction = ds_init.landIceFraction
        if 'landIceFraction' in ds:
            land_ice_fraction = ds.landIceFraction
        coupled = ds_init.landIceFloatingFraction
        if 'landIceGlcFloatingFraction' in ds:
            coupled = ds.landIceGlcFloatingFraction
        ds_exchange = xr.merge(
            [
                ds_exchange,
                compute_flux_sent_to_land_ice(
                    area,
                    ds,
                    land_ice_fraction,
                    coupled,
                    self.min_floating_fraction,
                ),
            ]
        )
        return ds_exchange

    def _daily_volume(self, ds_init):
        """
        Compute the ocean's daily volume budget from its daily global
        statistics and daily means
        """
        ds_means = rename_time_series_stats(
            xr.open_mfdataset(
                self.daily_mean_filenames,
                combine='nested',
                concat_dim='Time',
                decode_times=False,
                data_vars='minimal',
            ),
            prefix=DAILY_MEANS_PREFIX,
        )
        ds_stats = xr.open_mfdataset(
            self.daily_filenames,
            combine='nested',
            concat_dim='Time',
            decode_times=False,
            data_vars='minimal',
        )
        missing = [
            name
            for name in [
                'landIceFreshwaterFlux',
                'landIcePressure',
            ]
            if name not in ds_means
        ]
        if missing:
            self.logger.info(
                f"The ocean's daily means have no {', '.join(missing)}, so "
                f'the daily volume budget leaves out the terms that need them.'
            )
        return compute_daily_volume_budget(
            ds_means,
            ds_stats[['xtime', 'volumeCellGlobal']],
            ds_init,
            self.ref_density,
            self.tidal_forcing_type,
        )

    def _monthly_volume(self, ds, ds_init):
        """
        Compute the volume budget of the cells outside the tidally forced
        ones each month, from the snapshots of layer thickness and the
        monthly means
        """
        ds_mask = _open_without_time(TIDAL_MASK_FILENAME)
        interior = ds_mask.tidalInputMask.values == 0
        area = ds_init.areaCell.values
        days = []
        volumes = []
        if 'xtime' in ds_init:
            start = ds_init.xtime.values.item()
        else:
            # an initial condition without a time is at the start of year 1
            start = '0001-01-01_00:00:00'
        days.append(xtime_to_days(start))
        volumes.append(
            _interior_volume(ds_init.layerThickness, area, interior)
        )
        for filename in self.snapshot_filenames:
            ds_snapshot = xr.open_dataset(filename, decode_times=False)
            for t_index in range(ds_snapshot.sizes['Time']):
                ds_one = ds_snapshot.isel(Time=t_index)
                days.append(xtime_to_days(ds_one.xtime.values.item()))
                volumes.append(
                    _interior_volume(ds_one.layerThickness, area, interior)
                )
        missing = [
            name
            for name in ['normalLayerThicknessFlux', 'landIceFreshwaterFlux']
            if name not in ds
        ]
        if missing:
            self.logger.info(
                f"The ocean's monthly means have no {', '.join(missing)}, "
                f'so the monthly volume budget leaves out the terms that '
                f'need them.'
            )
        return compute_monthly_volume_budget(
            ds,
            np.array(days),
            np.array(volumes),
            ds_init,
            interior,
            self.ref_density,
        )

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


def compute_daily_volume_budget(
    ds_means,
    ds_stats,
    ds_init,
    ref_density,
    tidal_forcing_type=None,
):
    """
    Compute the ocean's daily volume budget

    The volume changes by the melt under the ice, by frazil, by the volume the
    tidal forcing adds in the cells whose sea-surface height it holds and by a
    small rest.  Frazil's volume is its thickness tendency where the daily
    means have it, and otherwise its freshwater flux, which leaves out frazil
    formed in the open ocean.  Water the land ice displaces as it grows heavier
    leaves through the tidally forced cells.  The tidal forcing's term comes
    from ``tidalLayerThicknessTendency`` where the forcing is a thickness
    source.  Forcing that sets the thickness directly leaves that tendency at
    zero, and no daily mean gives the exact flow out of those cells, so the
    budget then has no tidal term.  The land-ice load is an estimate from daily
    means.

    Parameters
    ----------
    ds_means : xarray.Dataset
        The ocean's daily means, renamed without their prefix, with
        ``xtime_startDaily`` and ``xtime_endDaily`` and any of
        ``landIceFreshwaterFlux``, ``frazilIceFreshwaterFlux``,
        ``frazilLayerThicknessTendency``,
        ``tidalLayerThicknessTendency`` and ``landIcePressure``

    ds_stats : xarray.Dataset
        The daily global statistics, with ``xtime`` and
        ``volumeCellGlobal`` at the end of each day

    ds_init : xarray.Dataset
        The initial condition and mesh, with ``areaCell``

    ref_density : float
        The reference density (kg m-3) by which the ocean converts its
        freshwater fluxes to thickness

    tidal_forcing_type : str, optional
        The run's ``config_tidal_forcing_type``, if it has tidal forcing.
        The tidal tendency is used only for ``thickness_source``.

    Returns
    -------
    ds_volume : xarray.Dataset
        The terms of the budget (m3) over each day, with the tidal forcing
        type, or ``none``, in its attribute ``tidal_forcing_type``
    """
    day_end = xtime_to_days(ds_means.xtime_endDaily.values)
    _, unique = np.unique(day_end, return_index=True)
    ds_means = ds_means.isel(Time=unique)
    day_end = day_end[unique]
    # the start is the first sample, which the compute interval puts after
    # the start of the day
    day_start = np.floor(xtime_to_days(ds_means.xtime_startDaily.values))
    seconds = 86400.0 * (day_end - day_start)

    # the statistics are instantaneous, so a day's change needs them at
    # both of its ends; a segment writes none at its start
    stats_seconds = np.round(86400.0 * xtime_to_days(ds_stats.xtime.values))
    volumes = dict(
        zip(stats_seconds, ds_stats.volumeCellGlobal.values, strict=True)
    )

    def volume_at(days):
        return np.array(
            [volumes.get(second, np.nan) for second in np.round(86400 * days)]
        )

    ds_volume = xr.Dataset()
    ds_volume.attrs['tidal_forcing_type'] = tidal_forcing_type or 'none'
    ds_volume['dayStart'] = ('Time', day_start)
    ds_volume['dayEnd'] = ('Time', day_end)
    for name in ['dayStart', 'dayEnd']:
        ds_volume[name].attrs = dict(
            long_name=f'{name[3:].lower()} of the day',
            units='days since 0001-01-01',
        )
    ds_volume['volumeChange'] = (
        'Time',
        volume_at(day_end) - volume_at(day_start),
    )
    ds_volume.volumeChange.attrs = dict(
        long_name="change in the ocean's volume", units='m3'
    )

    area = ds_init.areaCell
    volume, frazil_source = _melt_and_frazil(ds_means, area, ref_density)
    if volume is not None:
        ds_volume['meltAndFrazilVolume'] = ('Time', seconds * volume)
        ds_volume.meltAndFrazilVolume.attrs = dict(
            long_name='volume added by melt and frazil',
            units='m3',
            frazil=frazil_source,
        )

    if (
        tidal_forcing_type == 'thickness_source'
        and 'tidalLayerThicknessTendency' in ds_means
    ):
        # the tendency the tidal forcing adds, sampled every time step, is
        # exact; it is zero outside the tidally forced cells
        # a day without the means, as before a run wrote them, has no term
        rate = (ds_means.tidalLayerThicknessTendency * area).sum(
            dim=['nCells', 'nVertLevels'], min_count=1
        )
        ds_volume['tidalForcingInflow'] = ('Time', seconds * rate.values)
        ds_volume.tidalForcingInflow.attrs = dict(
            long_name='volume added by the tidal forcing',
            units='m3',
        )

    if 'landIcePressure' in ds_means:
        gravity = get_constant('standard_acceleration_of_gravity')
        load = (ds_means.landIcePressure * area).sum(dim='nCells').values / (
            ref_density * gravity
        )
        ds_volume['landIceLoad'] = ('Time', load)
        ds_volume.landIceLoad.attrs = dict(
            long_name=(
                'the land-ice pressure on the ocean, as a volume of '
                'seawater at the reference density'
            ),
            units='m3',
        )
        # the change from the day before, where the days follow each other
        change = np.full(len(load), np.nan)
        follows = day_start[1:] == day_end[:-1]
        change[1:] = np.where(follows, load[1:] - load[:-1], np.nan)
        ds_volume['landIceLoadChange'] = ('Time', change)
        ds_volume.landIceLoadChange.attrs = dict(
            long_name='change in the land-ice load from the day before',
            units='m3',
        )
    return ds_volume


def compute_monthly_volume_budget(
    ds_means, snapshot_days, snapshot_volumes, ds_mesh, interior, ref_density
):
    """
    Compute each month's volume budget of the cells outside the tidally
    forced ones

    Where the tidal forcing sets the forced cells' thickness directly, no
    output gives the volume it adds, but the cells outside them, the
    interior, have a closed budget: their volume changes by the melt and
    frazil in them and by the transport out across the edges they share
    with the forced cells.  The transport is the monthly mean of
    ``normalLayerThicknessFlux``, the thickness flux the ocean's continuity
    equation applies, sampled every time step, so the budget closes to
    round-off.

    Parameters
    ----------
    ds_means : xarray.Dataset
        The ocean's monthly means, renamed without their prefix, with
        ``xtime_startMonthly`` and any of ``normalLayerThicknessFlux``,
        ``landIceFreshwaterFlux``, ``frazilIceFreshwaterFlux`` and
        ``frazilLayerThicknessTendency``

    snapshot_days : numpy.ndarray
        The times (days since 0001-01-01) of the interior's volume

    snapshot_volumes : numpy.ndarray
        The interior's volume (m3) at those times

    ds_mesh : xarray.Dataset
        The mesh, with ``areaCell``, ``cellsOnEdge`` and ``dvEdge``

    interior : numpy.ndarray
        Whether each cell is outside the tidally forced cells

    ref_density : float
        The reference density (kg m-3) by which the ocean converts its
        freshwater fluxes to thickness

    Returns
    -------
    ds_volume : xarray.Dataset
        The terms of the interior's budget (m3) over each month: the volume
        change, which needs the volume at both ends of the month, the volume
        melt and frazil add and the transport out to the forced cells
    """
    months = [
        tuple(int(part) for part in _start_date(ds_means, t_index).split('-'))
        for t_index in range(ds_means.sizes['Time'])
    ]
    month_start = np.array(
        [month_start_days(year, month) for year, month in months]
    )
    month_end = np.array(
        [month_start_days(year, month + 1) for year, month in months]
    )
    seconds = 86400.0 * (month_end - month_start)

    volumes = dict(
        zip(
            np.round(86400.0 * snapshot_days),
            snapshot_volumes,
            strict=True,
        )
    )

    def volume_at(days):
        return np.array(
            [volumes.get(second, np.nan) for second in np.round(86400 * days)]
        )

    ds_volume = xr.Dataset()
    ds_volume['monthStart'] = ('Time', month_start)
    ds_volume['monthEnd'] = ('Time', month_end)
    for name in ['monthStart', 'monthEnd']:
        ds_volume[name].attrs = dict(
            long_name=f'{name[5:].lower()} of the month',
            units='days since 0001-01-01',
        )
    ds_volume['volumeChange'] = (
        'Time',
        volume_at(month_end) - volume_at(month_start),
    )
    ds_volume.volumeChange.attrs = dict(
        long_name='change in the volume outside the tidally forced cells',
        units='m3',
    )

    cells = np.flatnonzero(interior)
    area = ds_mesh.areaCell.isel(nCells=cells)
    ds_interior = ds_means.isel(nCells=cells)
    for name in ['frazilLayerThicknessTendency', 'frazilIceFreshwaterFlux']:
        if name in ds_interior:
            ds_interior[name] = _without_fill(ds_interior[name])
    volume, frazil_source = _melt_and_frazil(ds_interior, area, ref_density)
    if volume is not None:
        ds_volume['meltAndFrazilVolume'] = ('Time', seconds * volume)
        ds_volume.meltAndFrazilVolume.attrs = dict(
            long_name=(
                'volume added by melt and frazil outside the tidally forced '
                'cells'
            ),
            units='m3',
            frazil=frazil_source,
        )

    if 'normalLayerThicknessFlux' in ds_means:
        cells_on_edge = ds_mesh.cellsOnEdge.values - 1
        both = np.all(cells_on_edge >= 0, axis=1)
        first = np.where(both, cells_on_edge[:, 0], 0)
        second = np.where(both, cells_on_edge[:, 1], 0)
        edges = np.flatnonzero(
            np.logical_and(both, interior[first] != interior[second])
        )
        # the normal points from the edge's first cell to its second, so
        # the flux is out of the interior where the first cell is in it
        sign = np.where(interior[first[edges]], 1.0, -1.0)
        flux = _without_fill(ds_means.normalLayerThicknessFlux).isel(
            nEdges=edges
        )
        rate = (
            flux.sum(dim='nVertLevels')
            * xr.DataArray(sign * ds_mesh.dvEdge.values[edges], dims='nEdges')
        ).sum(dim='nEdges')
        ds_volume['outflow'] = ('Time', seconds * rate.values)
        ds_volume.outflow.attrs = dict(
            long_name='transport out to the tidally forced cells',
            units='m3',
        )
    return ds_volume


def _interior_volume(layer_thickness, area, interior):
    """The volume (m3) of the cells outside the tidally forced ones"""
    column = _without_fill(layer_thickness).sum(dim='nVertLevels').values
    return float(np.sum((column * area)[interior]))


def _melt_and_frazil(ds_means, area, ref_density):
    """
    The volume (m3 s-1) melt and frazil add each day, and where the frazil
    comes from: ``thickness tendency``, ``freshwater flux`` (an
    approximation), ``mixed`` or ``none``

    The melt's thickness flux is its freshwater flux over the reference
    density, as in MPAS-Ocean.  Frazil's volume is its thickness tendency,
    which includes frazil formed in the open ocean.  Its freshwater flux is
    only the frazil under the ice, so it is used, as an approximation, only
    on days without the tendency.
    """
    terms = []
    if 'landIceFreshwaterFlux' in ds_means:
        terms.append(
            (ds_means.landIceFreshwaterFlux * area).sum(dim='nCells').values
            / ref_density
        )
    frazil = None
    if 'frazilIceFreshwaterFlux' in ds_means:
        frazil = (ds_means.frazilIceFreshwaterFlux * area).sum(
            dim='nCells'
        ).values / ref_density
    from_tendency = np.zeros(ds_means.sizes['Time'], dtype=bool)
    if 'frazilLayerThicknessTendency' in ds_means:
        # a day without the tendency, as before a run wrote it, has none
        tendency = (
            (ds_means.frazilLayerThicknessTendency * area)
            .sum(dim=['nCells', 'nVertLevels'], min_count=1)
            .values
        )
        from_tendency = np.isfinite(tendency)
        frazil = (
            tendency
            if frazil is None
            else np.where(from_tendency, tendency, frazil)
        )
    if frazil is not None:
        terms.append(frazil)
    if not terms:
        return None, 'none'
    if frazil is None:
        source = 'none'
    elif np.all(from_tendency):
        source = 'thickness tendency'
    elif np.any(from_tendency):
        source = 'mixed'
    else:
        source = 'freshwater flux'
    return sum(terms), source


def _has_tidal_forcing(run):
    """Whether a run's namelist turns on tidal forcing"""
    try:
        value = run.namelist_option('config_use_tidal_forcing')
    except KeyError:
        return False
    return value.strip().strip('\'"').lower() in ('.true.', 'true', 't')


def read_initial_condition(prefix=''):
    """
    Read a run's initial condition and mesh, which hold its geometry and
    mesh, without a ``Time`` dimension

    Parameters
    ----------
    prefix : str, optional
        A prefix on the local names ``init.nc`` and ``mesh.nc``

    Returns
    -------
    ds_init : xarray.Dataset
        The initial condition with the mesh's variables it lacks
    """
    ds_init = _open_without_time(f'{prefix}{INIT_FILENAME}')
    ds_mesh = _open_without_time(f'{prefix}{MESH_FILENAME}')
    for name, variable in ds_mesh.data_vars.items():
        if name not in ds_init:
            ds_init[name] = variable
    return ds_init


def add_geometry_inputs(step, diagnostics, prefix=''):
    """
    Link the initial condition and mesh of a diagnostics step's run into
    another step

    Parameters
    ----------
    step : polaris.Step
        The step reading them with :py:func:`read_initial_condition`

    diagnostics : RunDiagnostics
        The diagnostics step of the run

    prefix : str, optional
        A prefix on the local names
    """
    for filename in [INIT_FILENAME, MESH_FILENAME]:
        step.add_input_file(
            filename=f'{prefix}{filename}',
            work_dir_target=f'{diagnostics.path}/{filename}',
        )


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


def compute_time_means(ds):
    """
    Compute the means of monthly fields over several months

    The ocean's state, each field in :py:data:`WET_MEAN_WEIGHTS`, is
    averaged over the months its column is wet, weighted by the thickness
    of its layer for a field on layers.  A column that is wet in no month
    holds only the thin film and keeps its plain mean.  Other fields, such
    as fluxes and transports, are averaged over all months.

    Parameters
    ----------
    ds : xarray.Dataset
        Monthly fields with a ``Time`` dimension and ``wetColumn``, whether
        each column is wet in each month

    Returns
    -------
    ds_mean : xarray.Dataset
        The means, with ``filmColumn``, the columns wet in no month, and
        ``partlyWetColumn``, those wet in only some months
    """
    wet = ds.wetColumn > 0
    ds_mean = ds.drop_vars('wetColumn').mean(dim='Time')
    for name, weight in WET_MEAN_WEIGHTS.items():
        if name in ds:
            ds_mean[name] = compute_wet_time_mean(
                ds[name], wet, None if weight is None else ds[weight]
            )
    count = wet.sum(dim='Time')
    ds_mean['filmColumn'] = (count == 0).astype(np.int8)
    ds_mean.filmColumn.attrs = dict(
        long_name=(
            'columns under grounded ice, or thinner than twice the minimum '
            'thickness of each of their active layers, in every month'
        )
    )
    ds_mean['partlyWetColumn'] = np.logical_and(
        count > 0, count < ds.sizes['Time']
    ).astype(np.int8)
    ds_mean.partlyWetColumn.attrs = dict(
        long_name='columns wet in only some months, whose means take those'
    )
    return ds_mean


def _open_without_time(filename):
    """Open a file, dropping a Time dimension of length one"""
    ds = xr.open_dataset(filename, decode_times=False)
    if 'Time' in ds.dims:
        ds = ds.isel(Time=0)
    return ds


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
    """Add the temperature, salinity and thickness of each column's bottom
    layer"""
    bottom = ds_init.maxLevelCell - 1
    for name in ['temperature', 'salinity', 'layerThickness']:
        ds[f'{name}Bottom'] = ds[name].isel(nVertLevels=bottom)
    return ds


def _add_wet_columns(ds, ds_init, geometry, min_thickness):
    """Add whether each column is wet, rather than holding only the thin
    film, in each month"""
    level_count = ds_init.maxLevelCell - ds_init.minLevelCell + 1
    film = get_film_columns(
        ds.ssh,
        ds_init.bottomDepth,
        level_count,
        geometry['landIceFraction'],
        geometry['landIceFloatingFraction'],
        min_thickness,
    )
    ds['wetColumn'] = np.logical_not(film).astype(np.int8)
    ds.wetColumn.attrs = dict(
        long_name='whether the column is wet, rather than holding only the '
        'thin film'
    )
    return ds


def _time_series(
    ds,
    ds_init,
    geometry,
    deep_draft,
    min_thickness,
    min_floating_fraction,
    restoring_x,
    ref_density,
):
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
    ds_ssh = compute_open_ocean_ssh_diagnostics(
        area,
        ds_init.xIsomipCell,
        ds.ssh,
        ds.density,
        thickness,
        ds_init.minLevelCell,
        ds_init.maxLevelCell,
        geometry['landIceFraction'],
        restoring_x,
        ref_density,
    )
    datasets = [ds_series, ds_film, ds_ssh]
    if 'landIceGlcFloatingFraction' in ds:
        # only a coupled run has the land-ice model's floating fraction
        datasets.append(
            compute_grounding_line_band_diagnostics(
                area,
                ds_init.xCell,
                ds_init.yCell,
                ds.landIceFreshwaterFlux,
                geometry['landIceFloatingFraction'],
                ds.landIceGlcFloatingFraction,
                min_floating_fraction,
            )
        )
        datasets.append(
            compute_flux_sent_to_land_ice(
                area,
                ds,
                geometry['landIceFraction'],
                ds.landIceGlcFloatingFraction,
                min_floating_fraction,
            )
        )
    return xr.merge(datasets)


def _streamfunction_strengths(
    ds, ds_init, geometry, dx, dz, restoring_x, bottom_slab
):
    """
    The range under the ice of the barotropic and overturning
    streamfunctions in each month, the barotropic streamfunction's
    extremum in the open ocean, and the open ocean's mean geostrophic
    height of the flow in a slab above the seafloor
    """
    floating = geometry['landIceFloatingFraction'] > 0.0
    land_ice_fraction = geometry['landIceFraction']
    open_ocean = get_open_ocean_mask(
        ds_init.xIsomipCell, land_ice_fraction, restoring_x
    )
    restoring = np.logical_and(
        land_ice_fraction == 0.0, ds_init.xIsomipCell >= restoring_x
    )
    seafloor = -float(
        ds_init.bottomDepth.where(np.logical_or(open_ocean, restoring)).max()
    )
    bsf_range = []
    osf_range = []
    gyre = []
    gyre_max = []
    gyre_min = []
    bottom_height = []
    for t_index in range(ds.sizes['Time']):
        ds_month = ds.isel(Time=slice(t_index, t_index + 1))
        floating_month = floating
        if 'Time' in floating.dims:
            floating_month = floating.isel(Time=t_index)
        open_month = open_ocean
        restoring_month = restoring
        if 'Time' in open_ocean.dims:
            open_month = open_ocean.isel(Time=t_index)
            restoring_month = restoring.isel(Time=t_index)
        bsf_cell = _cell_mean_of_vertices(
            ds_init, _barotropic_streamfunction(ds_init, ds_month.isel(Time=0))
        )
        bsf_range.append(_range_where(bsf_cell, floating_month))
        gyre.append(_extremum_where(bsf_cell, open_month))
        gyre_max.append(float(bsf_cell.where(open_month).max()))
        gyre_min.append(float(bsf_cell.where(open_month).min()))
        height = _bottom_geostrophic_height(
            ds_init, ds_month.isel(Time=0), seafloor, bottom_slab
        )
        bottom_height.append(
            _area_mean_where(height, ds_init.areaCell, open_month)
            - _area_mean_where(height, ds_init.areaCell, restoring_month)
        )
        osf = _overturning(ds_month, ds_init, dx, dz).isel(Time=0)
        under_ice = osf.x <= _ice_front_x(ds_init, floating_month)
        osf_range.append(_range_where(osf, under_ice))
    ds_strength = xr.Dataset()
    ds_strength['barotropicStrength'] = ('Time', np.array(bsf_range))
    ds_strength['overturningStrength'] = ('Time', np.array(osf_range))
    ds_strength['openOceanGyreStrength'] = ('Time', np.array(gyre))
    ds_strength['openOceanGyreMax'] = ('Time', np.array(gyre_max))
    ds_strength['openOceanGyreMin'] = ('Time', np.array(gyre_min))
    ds_strength['openOceanBottomGeostrophicSsh'] = (
        'Time',
        np.array(bottom_height),
    )
    ds_strength.barotropicStrength.attrs = dict(
        long_name='range of the barotropic streamfunction under the ice',
        units='Sv',
    )
    ds_strength.overturningStrength.attrs = dict(
        long_name='range of the overturning streamfunction under the ice',
        units='Sv',
        method=(
            'normalLayerThicknessFlux'
            if 'normalLayerThicknessFlux' in ds
            else 'monthly means of velocity and thickness'
        ),
    )
    ds_strength.openOceanGyreStrength.attrs = dict(
        long_name=(
            'the barotropic streamfunction of largest magnitude in the open '
            'ocean'
        ),
        units='Sv',
    )
    ds_strength.openOceanGyreMax.attrs = dict(
        long_name='the largest barotropic streamfunction in the open ocean',
        units='Sv',
    )
    ds_strength.openOceanGyreMin.attrs = dict(
        long_name='the smallest barotropic streamfunction in the open ocean',
        units='Sv',
    )
    ds_strength.openOceanBottomGeostrophicSsh.attrs = dict(
        long_name=(
            "the open ocean's mean geostrophic height of the flow above the "
            "seafloor, relative to the restoring region's"
        ),
        units='m',
    )
    return ds_strength


def _time_mean(ds, ds_init, geometry, draft_bin_width, dx, dz):
    """
    Compute the time means of maps and sections over the given months: the
    ocean's state over the months each column is wet, the fluxes and
    transports over all months
    """
    # the plain means, for the transports
    ds_all = ds.mean(dim='Time')
    ds_mean = compute_time_means(ds)
    floating_fraction = geometry['landIceFloatingFraction']
    if 'Time' in floating_fraction.dims:
        floating_fraction = floating_fraction.mean(dim='Time')
    land_ice_fraction = geometry['landIceFraction']
    if 'Time' in land_ice_fraction.dims:
        land_ice_fraction = land_ice_fraction.mean(dim='Time')
    draft = geometry['landIceDraft']
    if 'Time' in draft.dims:
        draft = draft.mean(dim='Time')

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
    ds_out['landIceFraction'] = land_ice_fraction
    ds_out['filmColumn'] = ds_mean.filmColumn
    ds_out['partlyWetColumn'] = ds_mean.partlyWetColumn
    top = ds_init.minLevelCell - 1
    for name, velocity in [
        ('uBoundaryLayer', 'velocityZonal'),
        ('vBoundaryLayer', 'velocityMeridional'),
    ]:
        ds_out[name] = ds_mean[velocity].isel(nVertLevels=top)
        ds_out[name].attrs = dict(
            long_name=f'{velocity} in the top layer', units='m s-1'
        )
    ds_out['iceDraft'] = draft
    ds_out.iceDraft.attrs = dict(long_name='ice draft', units='m')
    ds_out['bathymetry'] = -ds_init.bottomDepth
    ds_out.bathymetry.attrs = dict(
        long_name='elevation of the seafloor', units='m'
    )
    ds_out['barotropicStreamfunction'] = _barotropic_streamfunction(
        ds_init, ds_all
    )
    ds_out['overturningStreamfunction'] = _overturning(
        ds_all.expand_dims('Time'), ds_init, dx, dz
    ).isel(Time=0)

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
        'layerThicknessBottom',
    ]:
        ds_maps[name] = ds[name]
    ds_maps = ds_maps.astype('float32')
    # whether each column is wet, for means over several months
    ds_maps['wetColumn'] = ds.wetColumn
    return ds_maps


def _barotropic_streamfunction(ds_init, ds_month):
    """The barotropic streamfunction (Sv) on vertices, zero on the outer
    boundary"""
    return compute_barotropic_streamfunction(
        ds_init, ds_month, prefix='', quiet=True
    ).rename('barotropicStreamfunction')


def _bottom_geostrophic_height(ds_init, ds_month, seafloor, slab):
    """
    The geostrophic height (m) of the mean flow in a slab of the given
    thickness (m) above the seafloor at the given elevation (m), on cells
    """
    # mpas_tools keeps the layers whose middle is at or below min_depth
    # and at or above max_depth
    psi = compute_barotropic_streamfunction(
        ds_init,
        ds_month,
        prefix='',
        quiet=True,
        min_depth=seafloor + slab,
        max_depth=seafloor,
    )
    psi_cell = _cell_mean_of_vertices(ds_init, psi)
    gravity = get_constant('standard_acceleration_of_gravity')
    return ds_init.fCell * 1e6 * psi_cell / (gravity * slab)


def _area_mean_where(field, area_cell, mask):
    """The area-weighted mean of a field where a mask is true"""
    weights = area_cell.where(mask, 0.0)
    return float((field * weights).sum() / weights.sum())


def _cell_mean_of_vertices(ds_init, field_vertex):
    """Average a field on vertices to the cells"""
    vertices = ds_init.verticesOnCell - 1
    valid = vertices >= 0
    values = field_vertex.isel(nVertices=vertices.where(valid, 0))
    return values.where(valid).mean(dim='maxEdges')


def _overturning(ds, ds_init, dx, dz):
    """
    The overturning streamfunction (Sv) across lines of constant x, in the
    protocol's coordinates, at elevations shared by every line, integrated
    up from the seafloor: from the mean layer thickness flux across each
    edge where the means hold it, and otherwise from the means of velocity
    and thickness
    """
    ds_mesh = isomip_mesh(ds_init)
    x_min = float(ds_mesh.xCell.min())
    x_max = float(ds_mesh.xCell.max())
    x_lines = dx * np.arange(np.floor(x_min / dx) + 1, np.ceil(x_max / dx))
    top = dz * np.ceil(max(float(ds.ssh.max()), 0.0) / dz)
    bottom = -dz * np.ceil(float(ds_init.bottomDepth.max()) / dz)
    z = top - dz * np.arange(int(round((top - bottom) / dz)) + 1)
    thickness = _with_nan(ds.layerThickness)
    has_flux = 'normalLayerThicknessFlux' in ds
    if has_flux:
        layer_flux = _without_fill(ds.normalLayerThicknessFlux)

    columns = []
    for x_line in x_lines:
        line = get_line_edges(ds_mesh, 'x', x_line)
        if line.sizes['nLineEdges'] == 0:
            continue
        if has_flux:
            transport = (
                layer_flux.isel(nEdges=line.edgeIndex)
                * line.sign
                * line.dvEdge
            )
        else:
            transport = compute_line_transport(
                line, ds.normalVelocity, thickness.fillna(0.0)
            )
        z_top, z_bottom = compute_line_interfaces(line, ds.ssh, thickness)
        osf = compute_overturning_from_edge_transport(
            transport, z_top, z_bottom, z
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
        long_name=(
            'overturning streamfunction, minus the transport toward '
            'increasing x below each elevation'
        ),
        units='Sv',
        method=(
            'normalLayerThicknessFlux'
            if has_flux
            else 'monthly means of velocity and thickness'
        ),
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


def _extremum_where(field, mask):
    """The value of largest magnitude of a field where a mask is true"""
    values = field.where(mask, 0.0)
    return float(values.isel(nCells=int(np.abs(values).argmax())))


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


def _without_fill(field):
    """A monthly mean with the fill value of invalid layers set to zero"""
    return field.where(np.abs(field) < 1e30, 0.0)


def _with_nan(field):
    """A monthly mean with the fill value of invalid layers set to NaN"""
    return field.where(np.abs(field) < 1e30)
