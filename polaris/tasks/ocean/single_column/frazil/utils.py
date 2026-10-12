import matplotlib.pyplot as plt
import numpy as np

from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.tasks.ocean.single_column.thermo.analysis import CP0_SW

FRAZIL_RATE_UNITS = {
    'FrazilEnergyFlux': 'W m$^{-2}$',
    'FrazilMassFlux': 'kg m$^{-2}$ s$^{-1}$',
    'FrazilSaltFlux': 'kg m$^{-2}$ s$^{-1}$',
}


def _comparison_style(comparison_name, stepper_colors):
    """Return a consistent color and EOS line style for one comparison."""
    stepper, frazil_type = comparison_name.rsplit(' ', 1)
    return {
        'color': stepper_colors[stepper],
        'linestyle': '--' if frazil_type == 'FixedProperty' else '-',
    }


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
            expected_rate = frazil_rate[:count]
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
    """Return cell-mean state and freezing-point diagnostics."""
    thickness_name = (
        'PseudoThickness' if model == 'omega' else 'layerThickness'
    )
    cell_thickness = ds[thickness_name]
    thickness = cell_thickness.mean(dim='nCells')
    temperature = ds.temperature.mean(dim='nCells')
    salinity = ds.salinity.mean(dim='nCells')
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
