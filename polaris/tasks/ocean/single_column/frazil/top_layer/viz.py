import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.ocean.model import OceanIOStep, get_days_since_start
from polaris.tasks.ocean.single_column.thermo.analysis import CP0_SW
from polaris.viz import mplstyle_context


class TopLayerViz(OceanIOStep):
    """
    A step for plotting the heat content of the top layer as a function of
    time for each of the frazil top-layer forward runs

    Attributes
    ----------
    comparisons : dict
        A dictionary of forward step names and the relative paths to the
        steps, used to compare the results of the forward runs
    """

    def __init__(self, component, indir, init, comparisons, name='viz'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to

        init : polaris.Step
            The init step, used to link the initial condition

        comparisons : dict
            A dictionary of forward step names and the relative paths to the
            steps

        name : str, optional
            the name of the step
        """
        super().__init__(component=component, name=name, indir=indir)
        self.comparisons = dict(comparisons)
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )

    def run(self):
        """
        Plot the top-layer heat content time series
        """
        config = self.config
        rho_sw = get_constant('seawater_density_reference')
        heat_flux = config.getfloat(
            'single_column_forcing', 'latent_heat_flux'
        )
        time_step = config.getfloat('single_column', 'time_step')

        ds_init = self.open_model_dataset('init.nc', config=config)
        init = _diagnostics(ds_init, rho_sw, config)
        h_ct_init = float(init['h_ct'][0, 0])
        # heat content after one time step of surface cooling alone
        h_ct_one_step = h_ct_init + 1e-6 * heat_flux * time_step
        zoom_days = 5 * time_step / 86400.0

        series = []
        for comparison_name, comparison_path in self.comparisons.items():
            source = os.path.join(comparison_path, 'output.nc')
            target = f'{comparison_name}.nc'
            if not os.path.exists(source):
                self.logger.warning(
                    f'Missing comparison output for {comparison_name}: '
                    f'{source}'
                )
                continue
            if os.path.lexists(target):
                os.remove(target)
            os.symlink(source, target)
            ds = self.open_model_dataset(
                target, config=config, decode_times=True
            )
            # the model does not write a t=0 record, so prepend the init state
            t = np.concatenate([[0.0], get_days_since_start(ds)])
            run = _diagnostics(ds, rho_sw, config)
            fields = {
                key: np.concatenate([init[key], value], axis=0)
                for key, value in run.items()
            }
            series.append((comparison_name, t, fields))

        with mplstyle_context():
            _, axes = plt.subplots(3, 2, figsize=(12, 14))
            colors = plt.get_cmap('tab10')
            steppers = dict.fromkeys(
                name.split()[0] for name in self.comparisons
            )
            stepper_colors = {
                name: colors(index) for index, name in enumerate(steppers)
            }
            styles = {
                name: dict(
                    color=stepper_colors[name.split()[0]],
                    linestyle='--' if name.endswith('teos') else '-',
                )
                for name in self.comparisons
            }

            for ax, zoom in zip(axes[0], (False, True), strict=True):
                for comparison_name, t, fields in series:
                    ax.plot(
                        t,
                        fields['h_ct'][:, 0],
                        marker='.' if zoom else None,
                        label=comparison_name,
                        **styles[comparison_name],
                    )
                ax.plot(0.0, h_ct_init, 'ko', label='initial (freezing point)')
                ax.axhline(
                    h_ct_one_step,
                    linestyle='--',
                    color='k',
                    label='initial - one time step of cooling',
                )
                ax.set_ylabel('Top layer heat content (MJ m$^{-2}$)')
                if zoom:
                    ax.set_xlim(-0.1 * zoom_days, zoom_days)
                    ax.set_title('first 5 time steps')

            labels = (
                ('temperature', 'Top layer temperature (degC)'),
                ('thickness', 'Top layer thickness (m)'),
            )
            for ax, (key, label) in zip(axes[1], labels, strict=True):
                for comparison_name, t, fields in series:
                    ax.plot(
                        t,
                        fields[key][:, 0],
                        marker='.',
                        label=comparison_name,
                        **styles[comparison_name],
                    )
                    if key == 'temperature':
                        ax.plot(
                            t,
                            fields['ct_freezing'][:, 0],
                            ':',
                            color=styles[comparison_name]['color'],
                            label=f'{comparison_name} freezing point',
                        )
                ax.plot(0.0, float(init[key][0, 0]), 'ko')
                ax.set_xlim(-0.1 * zoom_days, zoom_days)
                ax.set_ylabel(label)
                if key == 'temperature':
                    ax.legend()

            for ax, level in zip(axes[2], (1, 2), strict=True):
                for comparison_name, t, fields in series:
                    anomaly = fields['h_ct'][:, level] - init['h_ct'][0, level]
                    ax.plot(
                        t,
                        anomaly,
                        label=comparison_name,
                        **styles[comparison_name],
                    )
                ax.axhline(0.0, linestyle='--', color='k')
                ax.set_ylabel(
                    f'Layer {level + 1} heat content anomaly (MJ m$^{{-2}}$)'
                )

            for ax in axes.flat:
                ax.set_xlabel('Time (days)')
            axes[0, 0].legend()
            plt.tight_layout(pad=0.5)
            plt.savefig('hCT.png')
            plt.close()


def _diagnostics(ds, rho_sw, config):
    """Cell-averaged thickness, temperature, heat content and freezing point"""
    thickness = ds.layerThickness.mean(dim='nCells')
    temperature = ds.temperature.mean(dim='nCells')
    salinity = ds.salinity.mean(dim='nCells')
    # mid-layer gauge pressure in Pa, from the accumulated layer thickness
    pressure = (
        rho_sw
        * get_constant('standard_acceleration_of_gravity')
        * (thickness.cumsum(dim='nVertLevels') - 0.5 * thickness)
    )
    ct_freezing = compute_ct_freezing(config, salinity, pressure=pressure)
    return dict(
        thickness=thickness.values,
        temperature=temperature.values,
        ct_freezing=np.asarray(ct_freezing),
        h_ct=1e-6 * rho_sw * CP0_SW * (thickness * temperature).values,
    )
