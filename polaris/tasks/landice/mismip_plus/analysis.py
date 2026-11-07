import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.landice.mismip_plus.diagnostics import compute_diagnostics
from polaris.tasks.landice.mismip_plus.cornford import MALI_2017_ENTRY
from polaris.tasks.landice.mismip_plus.output import read_output
from polaris.tasks.landice.mismip_plus.plot import (
    plot_global_stats,
    plot_grounding_line,
    plot_thickness_and_speed,
    plot_time_series,
)
from polaris.viz import mplstyle_context

# the times (years) at which to plot grounding lines
GROUNDING_LINE_YEARS = [0.0, 100.0, 200.0]


class Analysis(Step):
    """
    A step for computing the MISMIP+ diagnostics of an experiment and
    comparing them with Cornford et al. (2020)

    Attributes
    ----------
    experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
        The experiment

    previous : polaris.tasks.landice.mismip_plus.experiments.Experiment
        The experiment this one starts from, if any
    """

    def __init__(
        self,
        component,
        experiment,
        indir,
        spin_up,
        forward,
        cornford,
        previous,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
            The experiment

        indir : str
            the directory the step is in, to which ``name`` will be appended

        spin_up : polaris.tasks.landice.mismip_plus.spin_up.SpinUp
            The shared step with the steady state

        forward : polaris.tasks.landice.mismip_plus.forward.Forward
            The step that runs the experiment

        cornford : polaris.tasks.landice.mismip_plus.cornford.Cornford2020
            The shared step with the results of Cornford et al. (2020)

        previous : polaris.tasks.landice.mismip_plus.forward.Forward or None
            The step of the experiment this one starts from, if any
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.experiment = experiment
        self.previous = None if previous is None else previous.experiment

        self.add_input_file(
            filename='steady_state.nc',
            work_dir_target=f'{spin_up.path}/steady_state.nc',
        )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )
        self.add_input_file(
            filename='global_stats.nc',
            work_dir_target=f'{forward.path}/globalStats.nc',
        )
        names = [experiment.name]
        if previous is not None:
            self.add_input_file(
                filename='previous_output.nc',
                work_dir_target=f'{previous.path}/output.nc',
            )
            self.add_input_file(
                filename='previous_global_stats.nc',
                work_dir_target=f'{previous.path}/globalStats.nc',
            )
            names.append(previous.experiment.name)
        for name in names:
            self.add_input_file(
                filename=f'cornford2020_{name}.nc',
                work_dir_target=f'{cornford.path}/{name}.nc',
            )

        prefix = experiment.subdir
        for filename in [
            'diagnostics.nc',
            f'{prefix}_time_series.png',
            f'{prefix}_grounding_lines.png',
            f'{prefix}_thickness.png',
            f'{prefix}_surface_speed.png',
            f'{prefix}_global_stats_volume.png',
            f'{prefix}_global_stats_flux.png',
        ]:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        experiment = self.experiment
        prefix = experiment.subdir
        ds_mesh = xr.open_dataset('steady_state.nc')
        ds_mesh = ds_mesh.drop_dims('Time').load()

        ds_output = read_output('output.nc')
        ds_diag = compute_diagnostics(ds_output, ds_mesh=ds_mesh)
        ds_diag['Time'] = ds_output.Time
        write_netcdf(ds_diag, 'diagnostics.nc')

        series = []
        outputs = []
        references = []
        if self.previous is not None:
            ds_previous = read_output('previous_output.nc')
            ds_prev_diag = compute_diagnostics(ds_previous, ds_mesh=ds_mesh)
            ds_prev_diag['Time'] = ds_previous.Time
            series.append((self.previous.name, ds_prev_diag))
            outputs.append(ds_previous)
            references.append(
                _read_reference(f'cornford2020_{self.previous.name}.nc')
            )
        series.append((experiment.name, ds_diag))
        outputs.append(ds_output)
        references.append(
            _read_reference(f'cornford2020_{experiment.name}.nc')
        )

        reference_lines = []
        for index, ds_ref in enumerate(references):
            weertman = ds_ref.weertman.values
            mali = ds_ref.entry.values == MALI_2017_ENTRY
            for label, entries, kwargs in [
                (
                    'Cornford et al. (2020)',
                    ~weertman,
                    dict(color='0.8', linewidth=0.8),
                ),
                (
                    'Cornford et al. (2020), Weertman',
                    weertman,
                    dict(color='0.5', linewidth=0.8),
                ),
                (
                    'MALI (2017)',
                    mali,
                    dict(color='black', linewidth=1.2, linestyle='--'),
                ),
            ]:
                # only label each kind of reference once
                reference_lines.append(
                    (
                        label if index == 0 else None,
                        ds_ref.isel(entry=np.nonzero(entries)[0]),
                        kwargs,
                    )
                )

        plot_time_series(
            series,
            filename=f'{prefix}_time_series.png',
            title=f'MISMIP+ {experiment.name}',
            references=reference_lines,
        )

        self._plot_grounding_lines(ds_mesh, outputs, references, prefix)

        ds_end = ds_mesh.copy()
        for var in ['thickness', 'bedTopography', 'surfaceSpeed']:
            ds_end[var] = ds_output[var].isel(Time=-1)
        end_year = float(ds_output.Time.values[-1])
        plot_thickness_and_speed(
            ds_end,
            self.config,
            prefix=f'{prefix}_',
            title=f'at {end_year:g} a',
        )

        global_stats = []
        if self.previous is not None:
            global_stats.append(
                (self.previous.name, read_output('previous_global_stats.nc'))
            )
        global_stats.append((experiment.name, read_output('global_stats.nc')))
        plot_global_stats(
            global_stats,
            prefix=f'{prefix}_',
            title=f'MISMIP+ {experiment.name}',
        )

    def _plot_grounding_lines(self, ds_mesh, outputs, references, prefix):
        """
        Plot the grounding lines at 0, 100 and 200 years with those of MALI's
        2017 entry
        """
        with mplstyle_context():
            fig, ax = plt.subplots(figsize=(8.0, 3.0))
            colors = ['C0', 'C1', 'C2']
            for year, color in zip(GROUNDING_LINE_YEARS, colors, strict=True):
                ds = _find_time(ds_mesh, outputs, year)
                if ds is None:
                    continue
                plot_grounding_line(ax, ds, colors=color, linewidths=1.5)
                ax.plot([], [], color=color, label=f'{year:g} a')
                x_ref, y_ref = _find_mali_2017_grounding_line(references, year)
                if x_ref is not None:
                    ax.plot(
                        x_ref,
                        y_ref,
                        '.',
                        color=color,
                        markersize=1.0,
                        alpha=0.3,
                    )
            ax.plot([], [], '.', color='black', alpha=0.3, label='MALI (2017)')
            ax.set_xlim(300.0e3, 600.0e3)
            ax.set_ylim(0.0, 80.0e3)
            ax.set_aspect('equal')
            ax.xaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
            ax.yaxis.set_major_formatter(lambda x, pos: f'{x / 1e3:g}')
            ax.set_xlabel('x (km)')
            ax.set_ylabel('y (km)')
            ax.legend(loc='upper right', fontsize='small')
            ax.set_title(f'MISMIP+ {self.experiment.name} grounding lines')
            fig.savefig(f'{prefix}_grounding_lines.png', bbox_inches='tight')
            plt.close(fig)


def _read_reference(filename):
    """
    Read the gathered entries of Cornford et al. (2020) for one experiment
    """
    ds = xr.open_dataset(filename).load()
    entries = [
        value.decode() if isinstance(value, bytes) else str(value)
        for value in ds.entry.values
    ]
    ds['entry'] = ('entry', np.array(entries, dtype=object))
    ds['weertman'] = ds.weertman.astype(bool)
    if 'mali2017XGL' in ds:
        mali_index = entries.index(MALI_2017_ENTRY)
        ds['mali2017Time'] = (
            'nTimeMali2017',
            ds.time.isel(entry=mali_index).values[: ds.sizes['nTimeMali2017']],
        )
    return ds


def _find_mali_2017_grounding_line(references, year):
    """
    Find the grounding line of MALI's 2017 entry at a given year
    """
    for ds_ref in references:
        if 'mali2017XGL' not in ds_ref:
            continue
        ref_times = ds_ref.mali2017Time.values
        matches = np.nonzero(np.isclose(ref_times, year))[0]
        if len(matches) > 0:
            t_index = matches[0]
            return (
                ds_ref.mali2017XGL.values[:, t_index],
                ds_ref.mali2017YGL.values[:, t_index],
            )
    return None, None


def _find_time(ds_mesh, outputs, year):
    """
    Find the output at a given year, with the mesh variables
    """
    for ds_output in outputs:
        matches = np.nonzero(np.isclose(ds_output.Time.values, year))[0]
        if len(matches) > 0:
            ds = ds_mesh.copy()
            for var in ['thickness', 'bedTopography']:
                ds[var] = ds_output[var].isel(Time=matches[0])
            return ds
    return None
