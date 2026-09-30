import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.constants import get_constant
from polaris.ocean.model import OceanIOStep, get_days_since_start
from polaris.tasks.ocean.single_column.frazil.top_layer.viz import (
    FRAZIL_RATE_UNITS,
    _comparison_style,
    _diagnostics,
    _plot_conservation_residuals,
    _plot_frazil_fluxes,
)
from polaris.viz import mplstyle_context

COLUMNS = (
    ('temperature', 'Temperature (degC)'),
    ('thickness', 'PseudoThickness (m)'),
    ('salinity', 'Salinity (g/kg)'),
    ('heat_content', 'thickness x temperature (m degC)'),
)


class MeltShortViz(OceanIOStep):
    """
    A step for plotting the evolution of both layers of the melt_short
    forward runs, along with the frazil fluxes and conservation residuals

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
        Plot the two-layer evolution, frazil fluxes, and budget residuals.
        """
        config = self.config
        model = config.get('ocean', 'model')
        rho_sw = get_constant('seawater_density_reference')
        # no surface forcing is applied in this task
        heat_flux = 0.0
        frazil_steps = 10

        ds_init = self.open_model_dataset('init.nc', config=config)
        init = _diagnostics(ds_init, rho_sw, config, model)
        ds_init.close()

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
            days = np.asarray(get_days_since_start(ds), dtype=float)
            run = _diagnostics(ds, rho_sw, config, model)
            fields = {
                key: np.concatenate([init[key], value], axis=0)
                for key, value in run.items()
            }
            frazil_rates = None
            if model == 'omega':
                missing = [
                    name for name in FRAZIL_RATE_UNITS if name not in ds
                ]
                if missing:
                    self.logger.warning(
                        f'Missing frazil history fields for '
                        f'{comparison_name}: {", ".join(missing)}'
                    )
                else:
                    frazil_rates = {
                        name: np.asarray(ds[name].mean(dim='nCells').values)
                        for name in FRAZIL_RATE_UNITS
                    }
            series.append(
                {
                    'name': comparison_name,
                    'hours': np.concatenate(([0.0], days)) * 24.0,
                    'history_hours': days * 24.0,
                    'fields': fields,
                    'frazil_rates': frazil_rates,
                }
            )
            ds.close()

        stepper_names = list(
            dict.fromkeys(name.rsplit(' ', 1)[0] for name in self.comparisons)
        )
        with mplstyle_context():
            stepper_colors = {
                name: plt.get_cmap('tab10')(index)
                for index, name in enumerate(stepper_names)
            }
            styles = {
                name: _comparison_style(name, stepper_colors)
                for name in self.comparisons
            }
            _plot_layer_evolution(series, styles)
            if model == 'omega':
                diagnostic_series = [
                    item for item in series if item['frazil_rates'] is not None
                ]
                _plot_frazil_fluxes(
                    diagnostic_series, styles, heat_flux, frazil_steps
                )
                _plot_conservation_residuals(
                    diagnostic_series,
                    styles,
                    heat_flux,
                    rho_sw,
                    frazil_steps,
                    column_sum=True,
                )
            else:
                self.logger.info(
                    'Skipping frazil flux and residual plots for MPAS-Ocean; '
                    'the requested history fields are Omega-specific.'
                )


def _plot_layer_evolution(series, styles):
    """Plot the state of the warm top layer and the supercooled bottom one."""
    layers = (('Top layer', 0), ('Bottom layer', 1))
    fig, axes = plt.subplots(2, 4, figsize=(20, 9), sharex=True)
    for row, (layer_label, layer) in enumerate(layers):
        for col, (key, ylabel) in enumerate(COLUMNS):
            ax = axes[row, col]
            freeze_key = {
                'temperature': 'ct_freezing',
                'heat_content': 'heat_freezing',
            }.get(key)
            for item in series:
                name = item['name']
                fields = item['fields']
                ax.plot(
                    item['hours'],
                    fields[key][:, layer],
                    lw=2,
                    marker='o',
                    ms=5,
                    label=name,
                    **styles[name],
                )
                if freeze_key is not None:
                    ax.plot(
                        item['hours'],
                        fields[freeze_key][:, layer],
                        ':',
                        lw=1,
                        alpha=0.7,
                        color=styles[name]['color'],
                    )
            ax.set_ylabel(f'{layer_label}\n{ylabel}')
            ax.grid(alpha=0.3)
            if freeze_key is not None:
                ax.set_title(
                    'dotted = freezing point', fontsize=9, loc='right'
                )

    axes[0, 0].legend(fontsize=7, ncol=2)
    for ax in axes[-1]:
        ax.set_xlabel('time (hours)')
    fig.tight_layout()
    fig.savefig('layer-evolution.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
