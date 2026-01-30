import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.time import get_days_since_start
from polaris.ocean.vertical.diagnostics import depth_from_thickness
from polaris.viz import use_mplstyle

# TODO import rho_0 from constants


class Viz(OceanIOStep):
    """
    A step for plotting the results of a single-column test
    """

    def __init__(
        self,
        component,
        indir,
        ideal_age=False,
        comparisons=None,
        variables=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        ideal_age : bool, optional
            Whether the initial condition should include the ideal age tracer

        comparisons : dict, optional
            A dictionary of comparison datasets to use for validation

        variables : dict, optional
            A dictionary of variables to plot along with their units
        """
        super().__init__(component=component, name='viz', indir=indir)
        if ideal_age:
            # Include age tracer
            variables['iAge'] = 'seconds'
        self.comparisons = (
            dict(comparisons)
            if comparisons
            else {'forward': '../forward/output.nc'}
        )
        self.variables = (
            dict(variables)
            if variables
            else {
                'temperature': 'degC',
                'salinity': 'PSU',
                'velocity': 'm s$^{-1}$',
            }
        )
        self.add_input_file(
            filename='initial_state.nc', target='../init/initial_state.nc'
        )
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/output.nc',
            )
            self.add_input_file(
                filename=f'{comparison_name}_diags.nc',
                target=f'{comparison_path}/output/KPP_test.0001-01-01_00.00.00.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        use_mplstyle()

        ds_init = self.open_model_dataset('initial_state.nc')
        ds_init = ds_init.isel(Time=0)
        if 'zMid' in ds_init:
            z_mid_init = ds_init['zMid'].mean(dim='nCells')
        else:
            comparison_name = next(iter(self.comparisons))
            ds_comp = self.open_model_dataset(
                f'{comparison_name}.nc', decode_times=False
            )
            z_mid_init = ds_comp['zMid'].isel(Time=0).mean(dim='nCells')

        section = self.config['single_column']
        t_target = section.getfloat('run_duration')
        # t_target = 0.

        # Plot temperature and salinity profiles
        for field_name, field_units in self.variables.items():
            fig = plt.figure(figsize=(3, 5))
            colors = ['b', 'r', 'darkgreen']
            if field_name == 'velocity':
                if (
                    'velocityZonal' not in ds_comp.keys()
                    and 'velocityMeridional' not in ds_comp.keys()
                ):
                    continue
                ax = plt.subplot(111)
                for comparison_name, color in zip(
                    self.comparisons.keys(), colors, strict=False
                ):
                    if not os.path.exists(f'{comparison_name}.nc'):
                        continue
                    ds_comp = self.open_model_dataset(
                        f'{comparison_name}.nc', decode_times=False
                    )
                    t_arr = get_days_since_start(ds_comp)
                    t_index = np.argmin(np.abs(t_arr - t_target))
                    t_days = float(t_arr[t_index])
                    title = f'final time = {t_days:2.1g} days'
                    self.logger.info(
                        f'Plot {field_name} for {comparison_name} at {t_days} '
                        'days'
                    )
                    ds_comp = ds_comp.isel(Time=t_index)
                    z_mid_final = ds_comp['zMid'].mean(dim='nCells')
                    u_final = ds_comp['velocityZonal'].mean(dim='nCells')
                    v_final = ds_comp['velocityMeridional'].mean(dim='nCells')
                    ax.plot(
                        u_final,
                        z_mid_final,
                        '-',
                        color=color,
                        label=f'u {comparison_name}',
                    )
                    ax.plot(
                        v_final,
                        z_mid_final,
                        '--',
                        color=color,
                        label=f'v {comparison_name}',
                    )
                ax.set_xlabel('Velocity (m/s)')
                ax.set_ylabel('z (m)')
                ax.legend()
                plt.title(title)
                plt.tight_layout(pad=0.5)
                plt.savefig('velocity.png')
                plt.close()
            else:
                # Plot initial state if available
                if field_name in ds_init.keys():
                    var_init = ds_init[field_name].mean(dim='nCells')
                    plt.plot(var_init, z_mid_init, '--k', label='initial')

                for comparison_name, color in zip(
                    self.comparisons.keys(), colors, strict=False
                ):
                    if not os.path.exists(f'{comparison_name}.nc'):
                        continue
                    # Look for field_name in either output file
                    ds_comp = self.open_model_dataset(
                        f'{comparison_name}.nc', decode_times=False
                    )
                    ds_diags = self.open_model_dataset(
                        f'{comparison_name}_diags.nc', decode_times=False
                    )
                    if field_name in ds_comp.keys():
                        ds = ds_comp
                    elif field_name in ds_diags.keys():
                        ds = ds_diags
                    else:
                        self.logger.warn(
                            f'{field_name} not present in {comparison_name}.nc'
                        )
                        continue
                    t_arr = get_days_since_start(ds)
                    t_index = np.argmin(np.abs(t_arr - t_target))
                    t_days = float(t_arr[t_index])
                    ds_final = ds.isel(Time=t_index)
                    var_comp = ds_final[field_name].mean(dim='nCells')
                    if 'nVertLevelsP1' in var_comp.dims:
                        var_comp = var_comp.isel(nVertLevelsP1=slice(0, -1))
                    # TODO delete this line when MPAS-O bug is fixed
                    if field_name == 'RiTopOfCell':
                        var_comp[0] = np.nan
                    # TODO use this line when Omega zMid is correct
                    # z_mid_final = ds_comp['zMid'].mean(dim='nCells')
                    z_mid_final = depth_from_thickness(ds_final).mean(
                        dim='nCells'
                    )
                    plt.plot(
                        var_comp,
                        z_mid_final,
                        '-',
                        color=color,
                        label=comparison_name,
                    )
                title = f'final time = {t_days:2.1g} days'
                plt.ylim([-100, 0])
                if field_name == 'temperature':
                    plt.xlim([15, 20])
                else:
                    plt.xlim(auto=True)
                plt.xlabel(f'{field_name} ({field_units})')
                plt.ylabel('z (m)')
                fig.legend(loc='center right')
                plt.title(title)
                plt.tight_layout(pad=0.5)
                plt.savefig(f'{field_name}.png')
                plt.close()
