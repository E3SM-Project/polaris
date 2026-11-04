import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.analysis.product_step import ProductStep
from polaris.e3sm.analysis.calendar import xtime_to_days
from polaris.e3sm.analysis.runs import E3smRun
from polaris.landice.diagnostics import (
    grounding_line_on_row,
    thickness_above_flotation,
)
from polaris.namelist import ingest
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    LANDICE_FILENAME,
)
from polaris.tasks.e3sm.analysis.misomip.exchange import (
    LANDICE_STATS_STREAM,
)
from polaris.viz.time_series import Series, plot_time_series

#: The MISMIP+ experiment each coupled experiment is compared with, and the
#: protocol's year that experiment starts in
MISMIP_PLUS_EXPERIMENTS = {
    'iceocean1r': ('Ice1r', 0.0),
    'iceocean1ra': ('Ice1ra', 100.0),
}

#: The config section naming the MISMIP+ output the coupled runs are
#: compared with
MISMIP_PLUS_SECTION = 'misomip_analysis_mismip_plus'

#: The standalone MALI runs of a MISMIP+ experiment that may be compared:
#: the config option's suffix and the label's suffix
REFERENCE_RUNS = [
    ('forward', ''),
    ('monthly_forward', ', monthly-forced steps'),
]

#: The quantities compared: the variable in MALI's global statistics and in
#: Cornford et al. (2020), the file's stem, the title, the y label and the
#: scale
QUANTITIES = [
    (
        'volumeAboveFloatation',
        'iceVAF',
        'volume_above_flotation',
        'Volume above flotation',
        'volume (km$^3$)',
        1e-9,
    ),
    (
        'groundedIceArea',
        'groundedArea',
        'grounded_area',
        'Grounded area',
        'area (km$^2$)',
        1e-6,
    ),
]

#: The y label and scale of the grounding line's position
GROUNDING_LINE_AXIS = ('x (km)', 1e-3)


class IceSheetComparison(ProductStep):
    """
    A step that compares the ice sheet of a coupled run with MALI's
    standalone runs of the matching MISMIP+ experiment and with the
    entries of Cornford et al. (2020)

    Each run is plotted against the years since its experiment started.
    The volume above flotation and grounded area come from each MALI run's
    global statistics, every time step, and the grounding line on the
    centerline from each run's history.

    Attributes
    ----------
    mismip_experiment : str
        The MISMIP+ experiment, such as ``Ice1r``

    start_year : float
        The protocol's year the MISMIP+ experiment starts in

    stats_filenames : list of str
        The local names of the coupled MALI's global statistics, in order

    start : float
        The start of the coupled run, in days since the start of year 1

    references : list of tuple
        The label and local prefix of each standalone MALI run compared

    has_cornford : bool
        Whether the entries of Cornford et al. (2020) are compared

    section_y : float
        The y (m) of the centerline
    """

    def __init__(self, component, subdir, case, diagnostics, experiment):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        case : polaris.e3sm.analysis.case.E3smCase
            The case of the coupled run

        diagnostics : RunDiagnostics
            The diagnostics step of the case's run, which has MALI's
            history

        experiment : str
            The coupled experiment, a key of
            :py:data:`MISMIP_PLUS_EXPERIMENTS`
        """
        super().__init__(
            component=component,
            name='ice_sheet_comparison',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.mismip_experiment, self.start_year = MISMIP_PLUS_EXPERIMENTS[
            experiment
        ]
        self.add_input_file(
            filename=LANDICE_FILENAME,
            work_dir_target=f'{diagnostics.path}/{LANDICE_FILENAME}',
        )
        self.add_dependency(diagnostics)
        landice = E3smRun(case.case_dir, 'mali')
        self.stats_filenames = []
        for stream_file in landice.find_stream_files(LANDICE_STATS_STREAM):
            filename = os.path.join(
                'landice_stats', os.path.basename(stream_file.path)
            )
            self.add_input_file(filename=filename, target=stream_file.path)
            self.stats_filenames.append(filename)
        self.start = (
            xtime_to_days(f'{case.get_value("RUN_STARTDATE")}_00:00:00')
            + float(case.get_value('START_TOD')) / 86400.0
        )
        self.references = []
        self.has_cornford = False
        self.section_y = 0.0

    def setup(self):
        """
        Link the MISMIP+ output the config names
        """
        super().setup()
        config = self.config
        self.section_y = config.getfloat('misomip_analysis', 'section_y')
        section = config[MISMIP_PLUS_SECTION]
        name = self.mismip_experiment.lower()
        self.references = []
        for suffix, label_suffix in REFERENCE_RUNS:
            path = section.get(f'{name}_{suffix}', '').strip()
            if not path:
                continue
            prefix = f'{suffix}_'
            for filename in [
                'globalStats.nc',
                'output.nc',
                'landice_grid.nc',
                'namelist.landice',
            ]:
                self.add_input_file(
                    filename=f'{prefix}{filename}',
                    target=os.path.join(os.path.abspath(path), filename),
                )
            self.references.append(
                (f'MALI {self.mismip_experiment}{label_suffix}', prefix)
            )
        cornford_dir = section.get('cornford2020_dir', '').strip()
        self.has_cornford = bool(cornford_dir)
        if self.has_cornford:
            self.add_input_file(
                filename='cornford2020.nc',
                target=os.path.join(
                    os.path.abspath(cornford_dir),
                    f'{self.mismip_experiment}.nc',
                ),
            )

    def run(self):
        """
        Plot the comparisons
        """
        coupled_stats = _stats_series(
            read_landice_stats(self.stats_filenames), self.start
        )
        ds_landice = xr.open_dataset(LANDICE_FILENAME)
        coupled_gl_years = (ds_landice.daysSince0001.values - self.start) / (
            365.0
        )
        end_year = max(
            1.0, float(np.nanmax(coupled_stats['years'])), coupled_gl_years[-1]
        )
        references = [
            (label, self._reference(prefix))
            for label, prefix in self.references
        ]
        cornford = None
        if self.has_cornford:
            cornford = xr.open_dataset('cornford2020.nc')

        coupled_label = 'MALI coupled to the ocean'
        for (
            stats_name,
            cornford_name,
            stem,
            title,
            ylabel,
            scale,
        ) in QUANTITIES:
            lines = [
                Series(
                    coupled_stats['years'],
                    scale * coupled_stats[stats_name],
                    coupled_label,
                )
            ]
            for label, reference in references:
                lines.append(
                    Series(
                        reference['years'],
                        scale * reference[stats_name],
                        label,
                        linestyle='--',
                    )
                )
            ensemble = _cornford_members(
                cornford, cornford_name, scale, self.start_year
            )
            title = f'{title}, {self.mismip_experiment}'
            self._plot(lines, ensemble, stem, title, ylabel, end_year)
            self._plot_differences(lines, stem, title, ylabel, end_year)

        ylabel, scale = GROUNDING_LINE_AXIS
        lines = [
            Series(
                coupled_gl_years,
                scale * ds_landice.xGL.values,
                coupled_label,
                marker='.',
            )
        ]
        for label, reference in references:
            lines.append(
                Series(
                    reference['glYears'],
                    scale * reference['xGL'],
                    label,
                    linestyle='--',
                    marker='.',
                )
            )
        ensemble = _cornford_members(cornford, 'xGL', scale, self.start_year)
        title = (
            f'Grounding line on y = {1e-3 * self.section_y:g} km, '
            f'{self.mismip_experiment}'
        )
        stem = 'grounding_line_position'
        self._plot(lines, ensemble, stem, title, ylabel, end_year)
        self._plot_differences(lines, stem, title, ylabel, end_year)

    def _reference(self, prefix):
        """Read a standalone MALI run's global statistics and history"""
        ds_stats = read_landice_stats([f'{prefix}globalStats.nc'])
        reference = _stats_series(ds_stats, 365.0 * (self.start_year - 1.0))
        ds_mesh = xr.open_dataset(
            f'{prefix}landice_grid.nc', decode_times=False
        )
        if 'Time' in ds_mesh.dims:
            ds_mesh = ds_mesh.isel(Time=0)
        ds_out = xr.open_dataset(f'{prefix}output.nc', decode_times=False)
        options = dict()
        for record in ingest(f'{prefix}namelist.landice').values():
            options.update(record)
        ice_density = float(options['config_ice_density'])
        ocean_density = float(options['config_ocean_density'])
        bed = (
            ds_out.bedTopography
            if 'bedTopography' in ds_out
            else (ds_mesh.bedTopography)
        )
        haf = thickness_above_flotation(
            ds_out.thickness, bed, ice_density, ocean_density
        )
        reference['xGL'] = grounding_line_on_row(
            haf, ds_mesh, y=self.section_y
        ).values
        reference['glYears'] = (
            xtime_to_days(ds_out.xtime.values)
            - 365.0 * (self.start_year - 1.0)
        ) / 365.0
        return reference

    def _plot(self, lines, ensemble, stem, title, ylabel, end_year):
        """Plot one quantity and write its data"""
        plot_time_series(
            lines,
            f'{stem}.png',
            ylabel=ylabel,
            xlabel='time since the experiment started (years)',
            title=title,
            ensemble=ensemble,
            ensemble_label='Cornford et al. (2020) range',
            xlim=(0.0, end_year),
            legend_outside=True,
        )
        ds = xr.Dataset()
        for index, line in enumerate(lines):
            ds[f'time{index}'] = (f'nTime{index}', line.time)
            ds[f'values{index}'] = (f'nTime{index}', line.values)
            ds[f'values{index}'].attrs = dict(long_name=line.label)
        write_netcdf(ds, f'{stem}.nc')
        self.add_product(
            plot=f'{stem}.png',
            data=f'{stem}.nc',
            group='ice_sheet',
            gallery='mismip_plus_comparison',
            title=title,
        )

    def _plot_differences(self, lines, stem, title, ylabel, end_year):
        """Plot the coupled run, the first line, less each standalone run,
        interpolated to the coupled run's times within the standalone run's
        times"""
        if len(lines) < 2:
            return
        coupled = lines[0]
        differences = []
        for line in lines[1:]:
            within = np.logical_and(
                coupled.time >= line.time[0], coupled.time <= line.time[-1]
            )
            differences.append(
                Series(
                    coupled.time[within],
                    coupled.values[within]
                    - np.interp(coupled.time[within], line.time, line.values),
                    f'coupled less {line.label}',
                    linestyle=line.linestyle,
                    marker='.',
                )
            )
        self._plot(
            differences,
            None,
            f'{stem}_difference',
            f'{title}: coupled less standalone',
            ylabel,
            end_year,
        )


def read_landice_stats(filenames):
    """
    Read MALI's global statistics, each time step once

    Parameters
    ----------
    filenames : list of str
        The files, in order

    Returns
    -------
    ds : xarray.Dataset
        ``days`` (days since the start of year 1) and the volume above
        flotation, grounded area and ice volume, along ``Time``
    """
    names = ['volumeAboveFloatation', 'groundedIceArea', 'totalIceVolume']
    datasets = []
    for filename in filenames:
        with xr.open_dataset(filename, decode_times=False) as ds:
            ds_stats = ds[names].load()
            ds_stats['days'] = ('Time', xtime_to_days(ds.xtime.values))
            datasets.append(ds_stats)
    ds = xr.concat(datasets, dim='Time')
    _, unique = np.unique(ds.days.values, return_index=True)
    return ds.isel(Time=unique)


def _stats_series(ds, start):
    """The global statistics as arrays, with the years since a start"""
    series = {name: ds[name].values for name in ds.data_vars}
    series['years'] = (ds.days.values - start) / 365.0
    return series


def _cornford_members(cornford, name, scale, start_year):
    """The entries of Cornford et al. (2020) for one quantity, against the
    years since the experiment started"""
    if cornford is None:
        return None
    members = []
    for index in range(cornford.sizes['entry']):
        time = cornford.time.isel(entry=index).values
        values = cornford[name].isel(entry=index).values
        valid = np.logical_and(np.isfinite(time), np.isfinite(values))
        if valid.any():
            members.append(
                Series(
                    time[valid] - start_year,
                    scale * values[valid],
                    str(cornford.entry.values[index]),
                )
            )
    return members
