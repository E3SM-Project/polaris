import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    compute_mixed_layer_n2,
    compute_potential_energy,
    get_frontal_cell_mask,
)
from polaris.tasks.ocean.mixed_layer_eddies.flux import (
    analyze_combined_flux,
    get_snapshot_days,
)
from polaris.tasks.ocean.mixed_layer_eddies.forward import MLE_SETTINGS
from polaris.tasks.ocean.mixed_layer_eddies.resolved.analysis import (
    SEGMENTS as RESOLVED_SEGMENTS,
)
from polaris.tasks.ocean.mixed_layer_eddies.viz import plot_surface_salinity
from polaris.viz import mplstyle_context


class Analysis(OceanIOStep):
    """
    A step for reporting restratification and combined buoyancy flux.

    Potential-energy release and stratification are inspection diagnostics,
    not pass/fail criteria or direct targets for tuning the model coefficient.
    Combined buoyancy flux is compared with its scaling without line fitting.

    Attributes
    ----------
    coarse_runs : list of tuple
        The resolution directory and parameterization setting of each
        coarse run
    """

    def __init__(self, component, indir, resolved_steps, coarse_steps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        resolved_steps : dict of polaris.Step
            The shared ``init`` step and the forward steps of each segment of
            the resolved run

        coarse_steps : dict of dict of polaris.Step
            The shared steps at each coarse resolution, keyed by the
            resolution's directory name and then the step name
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='mesh_resolved.nc',
            work_dir_target=f'{resolved_steps["init"].path}/culled_mesh.nc',
        )
        for segment in RESOLVED_SEGMENTS:
            self.add_input_file(
                filename=f'output_resolved_{segment}.nc',
                work_dir_target=f'{resolved_steps[segment].path}/output.nc',
            )
        self.add_input_file(
            filename='eddy_resolved.nc',
            work_dir_target=f'{resolved_steps["eddies"].path}/eddy_output.nc',
        )
        self.coarse_runs = []
        for resdir, steps in coarse_steps.items():
            self.add_input_file(
                filename=f'mesh_{resdir}.nc',
                work_dir_target=f'{steps["init"].path}/culled_mesh.nc',
            )
            for mle in MLE_SETTINGS:
                forward = steps[f'forward_{mle}']
                self.add_input_file(
                    filename=f'output_{resdir}_{mle}.nc',
                    work_dir_target=f'{forward.path}/output.nc',
                )
                self.coarse_runs.append((resdir, mle))
                self.add_input_file(
                    filename=f'eddy_{resdir}_{mle}.nc',
                    work_dir_target=f'{forward.path}/eddy_output.nc',
                )
        self.add_output_file(filename='restratification.csv')
        self.add_output_file(filename='potential_energy.png')
        self.add_output_file(filename='mixed_layer_n2.png')
        self.add_output_file(filename='final_surface_salinity.png')
        self.add_output_file(filename='combined_buoyancy_flux.png')
        self.add_output_file(filename='combined_buoyancy_flux.csv')
        self.add_output_file(filename='combined_buoyancy_flux_average.csv')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger
        section = config['mixed_layer_eddies_analysis']
        adjustment_days = section.getfloat('adjustment_days')

        series = {}
        ds_mesh = self.open_model_dataset('mesh_resolved.nc')
        filenames = [
            f'output_resolved_{segment}.nc' for segment in RESOLVED_SEGMENTS
        ]
        series['resolved'] = self._compute_series(ds_mesh, filenames)
        end_day = float(series['resolved'][0][-1])
        for resdir, mle in self.coarse_runs:
            ds_mesh = self.open_model_dataset(f'mesh_{resdir}.nc')
            series[f'{resdir}_{mle}'] = self._compute_series(
                ds_mesh, [f'output_{resdir}_{mle}.nc'], end_day=end_day
            )

        releases = {
            name: _pe_release(days, pe, adjustment_days)
            for name, (days, pe, _) in series.items()
        }
        resolved_release = releases['resolved']

        lines = ['run,pe_release_J_m-2,ratio_to_resolved']
        lines.append(f'resolved,{resolved_release:.6e},1.0')
        for name, release in releases.items():
            if name == 'resolved':
                continue
            ratio = release / resolved_release
            lines.append(f'{name},{release:.6e},{ratio:.4f}')
        with open('restratification.csv', 'w') as csv_file:
            csv_file.write('\n'.join(lines) + '\n')
        logger.info('\n'.join(lines))

        _plot_series(
            series,
            index=1,
            ylabel=r'PE - PE(day 1) (J m$^{-2}$)',
            filename='potential_energy.png',
            relative=True,
        )
        _plot_series(
            series,
            index=2,
            ylabel=r'mixed-layer $N^2$ (s$^{-2}$)',
            filename='mixed_layer_n2.png',
            relative=False,
        )

        self._plot_final_surface_salinity(end_day)
        self._analyze_combined_flux()

    def _analyze_combined_flux(self):
        """Compare time-averaged combined transport within each simulation."""
        runs = [('resolved', 'mesh_resolved.nc', 'eddy_resolved.nc', False)]
        runs.extend(
            (
                f'{resdir}_{mle}',
                f'mesh_{resdir}.nc',
                f'eddy_{resdir}_{mle}.nc',
                mle == 'on',
            )
            for resdir, mle in self.coarse_runs
        )
        analyze_combined_flux(self, runs)

    def _plot_final_surface_salinity(self, end_day):
        """
        Plot surface salinity at the common analysis endpoint: the resolved
        run on the top row and a row for each coarse resolution
        """
        ds_mesh = self.open_model_dataset('mesh_resolved.nc')
        ds = self.open_model_dataset(
            f'output_resolved_{RESOLVED_SEGMENTS[-1]}.nc'
        )
        ds = ds.isel(Time=-1).load()
        surface = ds.salinity.isel(nVertLevels=0)
        vmin = float(surface.min())
        vmax = float(surface.max())

        resdirs = list(dict.fromkeys(resdir for resdir, _ in self.coarse_runs))
        nrows = len(resdirs) + 1
        ncols = len(MLE_SETTINGS)
        with mplstyle_context():
            fig, axes = plt.subplots(
                nrows,
                ncols,
                figsize=(4.0 * ncols, 2.9 * nrows),
                constrained_layout=True,
                squeeze=False,
            )
            for ax in axes[0, 1:]:
                ax.set_axis_off()
            collection = plot_surface_salinity(
                axes[0, 0], ds_mesh, ds, 'resolved', vmin, vmax
            )
            for row, resdir in enumerate(resdirs, start=1):
                ds_mesh = self.open_model_dataset(f'mesh_{resdir}.nc')
                for col, mle in enumerate(MLE_SETTINGS):
                    ds = self.open_model_dataset(f'output_{resdir}_{mle}.nc')
                    days = get_snapshot_days(ds)
                    indices = np.flatnonzero(
                        np.isclose(days, end_day, rtol=0.0, atol=1.0e-10)
                    )
                    if len(indices) != 1:
                        raise ValueError(
                            f'{resdir} {mle}: expected one daily snapshot '
                            f'at day {end_day:g}'
                        )
                    plot_surface_salinity(
                        axes[row, col],
                        ds_mesh,
                        ds.isel(Time=int(indices[0])).load(),
                        f'{resdir} {mle}',
                        vmin,
                        vmax,
                    )
            fig.colorbar(
                collection,
                ax=axes,
                extend='both',
                shrink=0.5,
                label=r'surface salinity (g kg$^{-1}$)',
            )
            fig.savefig('final_surface_salinity.png', dpi=150)
            plt.close(fig)

    def _compute_series(self, ds_mesh, filenames, end_day=None):
        """
        Compute daily time series of potential energy and of mixed-layer
        stratification in the frontal zone for one run

        If ``end_day`` is supplied, exclude snapshots after that absolute
        simulation day and require the series to reach it. This aligns
        coarse runs with the resolved run's endpoint. If ``None``, include
        all available snapshots.
        """
        config = self.config
        section = config['mixed_layer_eddies_analysis']
        frontal_zone_fraction = section.getfloat('frontal_zone_fraction')
        ml_depth = config.getfloat('mixed_layer_eddies', 'mixed_layer_depth')
        cell_mask = get_frontal_cell_mask(ds_mesh, frontal_zone_fraction)

        pe = []
        n2 = []
        sample_days = []
        for filename in filenames:
            ds = self.open_model_dataset(filename)
            for index, day in enumerate(get_snapshot_days(ds)):
                if end_day is not None and day > end_day + 1.0e-10:
                    continue
                ds_time = ds.isel(Time=index).load()
                sample_days.append(day)
                pe.append(
                    float(compute_potential_energy(config, ds_mesh, ds_time))
                )
                n2.append(
                    float(
                        compute_mixed_layer_n2(
                            config, ds_mesh, ds_time, cell_mask, ml_depth
                        )
                    )
                )
        days = np.array(sample_days, dtype=float)
        if (
            len(days) == 0
            or np.any(np.diff(days) <= 0.0)
            or (end_day is not None and abs(days[-1] - end_day) > 1.0e-10)
        ):
            raise ValueError(
                'Daily analysis requires increasing timestamps and '
                'coverage through the common endpoint'
            )
        return days, np.array(pe), np.array(n2)


def _pe_release(days, pe, adjustment_days):
    """
    The potential energy released between the end of the Rossby adjustment
    and the end of the run (J m-2, positive for release)
    """
    start = np.interp(adjustment_days, days, pe)
    return float(start - pe[-1])


def _plot_series(series, index, ylabel, filename, relative):
    """
    Plot a time series of each run
    """
    with mplstyle_context():
        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        colors: dict[str, str] = {}
        for name, values in series.items():
            days = values[0]
            data = values[index]
            if relative:
                data = data - data[0]
            if name == 'resolved':
                ax.plot(days, data, '-k', label=name)
                continue
            resdir, mle = name.rsplit('_', 1)
            if resdir not in colors:
                colors[resdir] = f'C{len(colors)}'
            style = ':' if mle == 'off' else '-'
            ax.plot(days, data, style, color=colors[resdir], label=name)
        ax.set_xlabel('time (days)')
        ax.set_ylabel(ylabel)
        ax.legend(fontsize='small', ncol=2)
        fig.savefig(filename, bbox_inches='tight')
        plt.close(fig)
