import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.ocean.model import OceanIOStep, get_days_since_start
from polaris.tasks.ocean.single_column.thermo.analysis import CP0_SW
from polaris.viz import mplstyle_context

FRAZIL_RATE_UNITS = {
    'FrazilEnergyFlux': 'W m$^{-2}$',
    'FrazilMassFlux': 'kg m$^{-2}$ s$^{-1}$',
    'FrazilSaltFlux': 'kg m$^{-2}$ s$^{-1}$',
}


class OneLayerViz(OceanIOStep):
    """
    A step for plotting the heat content of the top layer as a function of
    time for each of the frazil one-layer forward runs

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
        Plot top-layer evolution, frazil fluxes, and budget residuals.
        """
        config = self.config
        model = config.get('ocean', 'model')
        rho_sw = get_constant('seawater_density_reference')
        heat_flux = config.getfloat(
            'single_column_forcing', 'latent_heat_flux'
        )
        time_step = config.getfloat('single_column', 'time_step')
        zoom_steps = 5
        frazil_steps = 15

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
            _plot_layer_evolution(
                series,
                init,
                styles,
                heat_flux,
                time_step,
                rho_sw,
                zoom_steps,
            )
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
                )
            else:
                self.logger.info(
                    'Skipping frazil flux and residual plots for MPAS-Ocean; '
                    'the requested history fields are Omega-specific.'
                )


def _comparison_style(comparison_name, stepper_colors):
    """Return a consistent color and EOS line style for one comparison."""
    stepper, frazil_type = comparison_name.rsplit(' ', 1)
    return {
        'color': stepper_colors[stepper],
        'linestyle': '--' if frazil_type == 'FixedProperty' else '-',
    }


def _plot_layer_evolution(
    series, init, styles, heat_flux, time_step, rho_sw, zoom_steps
):
    """Plot the top-layer state and freezing point over full and zoom views."""
    rows = (
        ('temperature', 'Temperature (degC)'),
        ('salinity', 'Salinity (g/kg)'),
        ('thickness', 'PseudoThickness (m)'),
        ('heat_content', 'thickness x temperature (m degC)'),
    )
    top_layer = 0
    thickness_init = float(init['thickness'][0, top_layer])
    temperature_init = float(init['temperature'][0, top_layer])
    temp_reference = temperature_init + heat_flux * time_step / (
        CP0_SW * rho_sw * thickness_init
    )
    heat_reference = (
        thickness_init * temperature_init
        + heat_flux * time_step / (CP0_SW * rho_sw)
    )
    zoom_hours = zoom_steps * time_step / 3600.0

    fig, axes = plt.subplots(4, 2, figsize=(14, 16), sharex='col')
    for row, (key, ylabel) in enumerate(rows):
        for col, zoom in enumerate((False, True)):
            ax = axes[row, col]
            for item in series:
                name = item['name']
                fields = item['fields']
                hours = item['hours']
                end = min(len(hours), zoom_steps + 1) if zoom else len(hours)
                marker = {'marker': 'o', 'ms': 5} if zoom else {}
                ax.plot(
                    hours[:end],
                    fields[key][:end, top_layer],
                    lw=2,
                    label=name,
                    **marker,
                    **styles[name],
                )
                ax.plot(
                    0.0,
                    fields[key][0, top_layer],
                    '+',
                    ms=14,
                    mew=2,
                    zorder=5,
                    color=styles[name]['color'],
                )
                freeze_key = {
                    'temperature': 'ct_freezing',
                    'heat_content': 'heat_freezing',
                }.get(key)
                if freeze_key is not None:
                    ax.plot(
                        hours[:end],
                        fields[freeze_key][:end, top_layer],
                        ':',
                        lw=1,
                        alpha=0.7,
                        color=styles[name]['color'],
                    )
            ax.set_ylabel(ylabel)
            ax.grid(alpha=0.3)
            if zoom:
                ax.set_xlim(-0.1 * zoom_hours, zoom_hours)
            if key in ('temperature', 'heat_content'):
                ax.set_title(
                    'dotted = freezing point', fontsize=9, loc='right'
                )

    axes[0, 0].set_title('Top layer, full run (+ marks init.nc)', loc='left')
    axes[0, 1].set_title(
        f'Top layer, first {zoom_steps} steps (+ marks init.nc)', loc='left'
    )
    axes[0, 1].axhline(
        temp_reference,
        color='k',
        lw=1,
        ls='-.',
        label='one-step surface-heat reference',
    )
    axes[3, 1].axhline(
        heat_reference,
        color='k',
        lw=1,
        ls='-.',
        label='one-step surface-heat reference',
    )
    axes[0, 0].legend(fontsize=7, ncol=2)
    for ax in axes[-1]:
        ax.set_xlabel('time (hours)')
    fig.tight_layout()
    fig.savefig('layer-evolution.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def _plot_frazil_fluxes(series, styles, heat_flux, frazil_steps):
    """Plot Omega's per-step frazil energy, mass, and salt rates."""
    fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    for item in series:
        if item['frazil_rates'] is None:
            continue
        name = item['name']
        for ax, (variable, _units) in zip(
            axes, FRAZIL_RATE_UNITS.items(), strict=True
        ):
            count = min(
                frazil_steps,
                len(item['history_hours']),
                len(item['frazil_rates'][variable]),
            )
            ax.plot(
                item['history_hours'][:count],
                item['frazil_rates'][variable][:count],
                lw=2,
                marker='o',
                ms=5,
                label=name,
                **styles[name],
            )

    for ax, (variable, units) in zip(
        axes, FRAZIL_RATE_UNITS.items(), strict=True
    ):
        ax.set_ylabel(f'{variable}\n({units})')
        ax.grid(alpha=0.3)
    if heat_flux != 0.0:
        axes[0].axhline(
            heat_flux, color='k', ls='--', lw=1, label='surface heat flux'
        )
    axes[0].set_title(f'Frazil coupling terms, first {frazil_steps} steps')
    axes[0].legend(fontsize=7, ncol=2)
    axes[-1].set_xlabel('time (hours)')
    fig.tight_layout()
    fig.savefig('frazil-fluxes.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def _plot_conservation_residuals(
    series, styles, heat_flux, rho_sw, frazil_steps, column_sum=False
):
    """Plot per-step state-rate residuals for Omega.

    Frazil fluxes are column integrals, so ``column_sum`` is needed whenever
    frazil can act outside the top layer.
    """
    budget_vars = (
        'FrazilEnergyFlux',
        'FrazilMassFlux',
        'FrazilSaltFlux',
    )
    cp0_sw = CP0_SW
    fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    for item in series:
        if item['frazil_rates'] is None:
            continue
        fields = item['fields']
        name = item['name']
        if column_sum:
            thickness = fields['thickness'].sum(axis=1)
            temperature = (fields['thickness'] * fields['temperature']).sum(
                axis=1
            ) / thickness
            salinity = (fields['thickness'] * fields['salinity']).sum(
                axis=1
            ) / thickness
        else:
            thickness = fields['thickness'][:, 0]
            temperature = fields['temperature'][:, 0]
            salinity = fields['salinity'][:, 0]
        intervals = np.diff(item['hours']) * 3600.0
        state_values = (
            cp0_sw * rho_sw * thickness * temperature,
            rho_sw * thickness,
            rho_sw * thickness * salinity / 1000.0,
        )
        state_rates = [np.diff(values) / intervals for values in state_values]

        for ax, variable, rate in zip(
            axes, budget_vars, state_rates, strict=True
        ):
            frazil_rate = item['frazil_rates'][variable]
            count = min(frazil_steps, len(rate), len(frazil_rate))
            expected_rate = -frazil_rate[:count]
            if variable == 'FrazilEnergyFlux':
                expected_rate = expected_rate + heat_flux
            residual = rate[:count] - expected_rate
            mean_residual = np.mean(residual)
            ax.plot(
                item['history_hours'][:count],
                residual,
                lw=2,
                marker='o',
                ms=5,
                label=f'{name} res={mean_residual:.2e}',
                **styles[name],
            )

    for ax, (variable, units) in zip(
        axes, FRAZIL_RATE_UNITS.items(), strict=True
    ):
        ax.axhline(0.0, color='k', lw=1)
        budget = variable.removeprefix('Frazil').removesuffix('Flux')
        ax.set_ylabel(f'residual {budget}\n({units})')
        ax.legend(fontsize=7, ncol=2)
        ax.grid(alpha=0.3)
    axes[0].set_title(
        'Per-timestep column conservation residual '
        f'(state change - forcing and frazil), '
        f'first {frazil_steps} steps'
    )
    axes[-1].set_xlabel('time (hours)')
    fig.tight_layout()
    fig.savefig('conservation-residuals.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def _diagnostics(ds, rho_sw, config, model):
    """Return cell-mean top-layer state and freezing-point diagnostics."""
    thickness_name = (
        'PseudoThickness' if model == 'omega' else 'layerThickness'
    )
    cell_thickness = ds[thickness_name]
    thickness = cell_thickness.mean(dim='nCells')
    temperature = ds.temperature.mean(dim='nCells')
    salinity = ds.salinity.mean(dim='nCells')
    # Compute the freezing point per cell before taking its horizontal mean.
    pressure = (
        rho_sw
        * get_constant('standard_acceleration_of_gravity')
        * (cell_thickness.cumsum(dim='nVertLevels') - 0.5 * cell_thickness)
    )
    ct_freezing_cells = np.asarray(
        compute_ct_freezing(config, ds.salinity, pressure=pressure)
    )
    cell_axis = ds.salinity.get_axis_num('nCells')
    ct_freezing = ct_freezing_cells.mean(axis=cell_axis)
    heat_content = (cell_thickness * ds.temperature).mean(dim='nCells')
    heat_freezing = (cell_thickness.values * ct_freezing_cells).mean(
        axis=cell_axis
    )
    return dict(
        thickness=thickness.values,
        temperature=temperature.values,
        salinity=salinity.values,
        ct_freezing=ct_freezing,
        heat_content=heat_content.values,
        heat_freezing=heat_freezing,
    )
