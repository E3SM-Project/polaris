import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    compute_mixed_layer_n2,
    compute_potential_energy,
    get_frontal_cell_mask,
)
from polaris.tasks.ocean.mixed_layer_eddies.forward import MLE_SETTINGS
from polaris.viz import mplstyle_context


class Analysis(OceanIOStep):
    """
    A step for comparing the restratification of the coarse runs with that
    of the resolved run

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
            The shared ``init``, ``spinup`` and ``eddies`` steps of the
            resolved run

        coarse_steps : dict of dict of polaris.Step
            The shared steps at each coarse resolution, keyed by the
            resolution's directory name and then the step name
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='mesh_resolved.nc',
            work_dir_target=f'{resolved_steps["init"].path}/culled_mesh.nc',
        )
        for segment in ['spinup', 'eddies']:
            self.add_input_file(
                filename=f'output_resolved_{segment}.nc',
                work_dir_target=f'{resolved_steps[segment].path}/output.nc',
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
        self.add_output_file(filename='restratification.csv')
        self.add_output_file(filename='potential_energy.png')
        self.add_output_file(filename='mixed_layer_n2.png')

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
            'output_resolved_spinup.nc',
            'output_resolved_eddies.nc',
        ]
        series['resolved'] = self._compute_series(ds_mesh, filenames)
        for resdir, mle in self.coarse_runs:
            ds_mesh = self.open_model_dataset(f'mesh_{resdir}.nc')
            series[f'{resdir}_{mle}'] = self._compute_series(
                ds_mesh, [f'output_{resdir}_{mle}.nc']
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

        self._check(releases)

    def _compute_series(self, ds_mesh, filenames):
        """
        Compute daily time series of potential energy and of mixed-layer
        stratification in the frontal zone for one run
        """
        config = self.config
        section = config['mixed_layer_eddies_analysis']
        frontal_zone_fraction = section.getfloat('frontal_zone_fraction')
        ml_depth = config.getfloat('mixed_layer_eddies', 'mixed_layer_depth')
        cell_mask = get_frontal_cell_mask(ds_mesh, frontal_zone_fraction)

        pe = []
        n2 = []
        for filename in filenames:
            ds = self.open_model_dataset(filename)
            for index in range(ds.sizes['Time']):
                ds_time = ds.isel(Time=index).load()
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
        # daily output, starting at the end of the first day
        days = np.arange(1, len(pe) + 1, dtype=float)
        return days, np.array(pe), np.array(n2)

    def _check(self, releases):
        """
        Check the potential-energy release of the coarse runs against that
        of the resolved run
        """
        section = self.config['mixed_layer_eddies_analysis']
        mle_min = section.getfloat('mle_pe_ratio_min')
        mle_max = section.getfloat('mle_pe_ratio_max')
        off_max = section.getfloat('off_pe_ratio_max')
        resolved_release = releases['resolved']
        failures = []
        for name, release in releases.items():
            if name == 'resolved':
                continue
            ratio = release / resolved_release
            if name.endswith('_off'):
                if not ratio < off_max:
                    failures.append(
                        f'{name}: ratio {ratio:.3f} is not below {off_max}'
                    )
            elif not mle_min <= ratio <= mle_max:
                failures.append(
                    f'{name}: ratio {ratio:.3f} is outside '
                    f'[{mle_min}, {mle_max}]'
                )
        if failures:
            raise ValueError(
                'Potential-energy release after the Rossby adjustment, '
                'relative to the resolved run:\n  ' + '\n  '.join(failures)
            )


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
        for name, values in series.items():
            days = values[0]
            data = values[index]
            if relative:
                data = data - data[0]
            style = '-k' if name == 'resolved' else '-'
            if name.endswith('_off'):
                style = ':'
            elif name.endswith('_ffh08'):
                style = '--'
            ax.plot(days, data, style, label=name)
        ax.set_xlabel('time (days)')
        ax.set_ylabel(ylabel)
        ax.legend(fontsize='small', ncol=2)
        fig.savefig(filename, bbox_inches='tight')
        plt.close(fig)
