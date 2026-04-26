import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.vertical.diagnostics import depth_from_thickness
from polaris.ocean.model import OceanIOStep
from polaris.ocean.model import get_days_since_start
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
        self.comparisons = (
            dict(comparisons)
            if comparisons
            else {'forward': '../forward'}
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
        if ideal_age:
            # Include age tracer
            self.variables['iAge'] = 'seconds'
        self.add_input_file(
            filename='initial_state.nc', target='../init/initial_state.nc'
        )

    def setup(self):
        model = self.config.get('ocean', 'model')
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/output.nc',
            )
            if model == 'mpas-ocean':
                self.add_input_file(
                    filename=f'{comparison_name}_diags.nc',
                    target=f'{comparison_path}/output/KPP_test.0001-01-01_00.00.00.nc',
                )

    def run(self):
        """
        Run this step of the test case
        """
        use_mplstyle()
        model = self.config.get('ocean', 'model')
        section = self.config['single_column']
        if section.has_option('run_duration'):
            t_target = section.getfloat('run_duration')
        else:
            self.logger.info(
                'run_duration not found in config; using default plotting '
                'time of 10 days')
            t_target = 10.

        ds_list = []
        time_ds = []
        comparisons = dict()
        for comparison_name in self.comparisons.keys():
            if os.path.exists(f'{comparison_name}.nc'):
                # Remove missing comparison so it won't be used later
                comparisons[comparison_name] = self.comparisons[comparison_name]
                continue
        for comparison_name in comparisons.keys():
            if os.path.exists(f'../{comparison_name}/coeffs_reconstruct.nc'):
                ds_comp = self.open_model_dataset(
                    f'{comparison_name}.nc',
                    decode_times=True,
                    mesh_filename='../init/initial_state.nc',
                    reconstruct_variables=['normalVelocity'],
                    coeffs_filename=f'../{comparison_name}/coeffs_reconstruct.nc',
                )
            else:
                ds_comp = self.open_model_dataset(
                    f'{comparison_name}.nc',
                    decode_times=True,
                )
            t_arr = get_days_since_start(ds_comp)
            t_index = np.argmin(np.abs(t_arr - t_target))
            time_ds.append(float(t_arr[t_index]))
            ds_list.append(ds_comp.isel(Time=t_index))

        ds_init = self.open_model_dataset('initial_state.nc')
        ds_init = ds_init.isel(Time=0)
        z_mid_init = ds_init['zMid'].mean(dim='nCells')

        z_mid_final = z_mid_init
        self.logger.warn(
            'Using initial zMid values; may not represent '
            'plotted state'
        )

        # Plot depth profiles of variables
        for field_name, field_units in self.variables.items():
            curves_plotted = 0
            fig = plt.figure(figsize=(3, 5))
            colors = ['b', 'r', 'darkgreen']
            for comparison_name, ds_comp, t_days, color in zip(
                self.comparisons.keys(), ds_list, time_ds, colors, strict=False
            ):
                # TODO use this line when Omega zMid is correct
                #z_mid_final = ds_comp['zMid'].mean(dim='nCells')
                # TODO compare with z_mid computed from layerThickness
                #z_mid_final = depth_from_thickness(ds_comp).mean(
                #    dim='nCells'
                #)
                if field_name == 'velocity':
                    if (
                        'velocityZonal' not in ds_comp.keys()
                        and 'velocityMeridional' not in ds_comp.keys()
                    ):
                        self.logger.info(
                            '\tvelocityZonal,Meridional not found; skipping plot'
                            f'for {comparison_name}'
                        )
                        continue
                    self.logger.info(
                        f'Plot {field_name} for {comparison_name} at {t_days} '
                        'days'
                    )
                    u_final = ds_comp['velocityZonal'].mean(dim='nCells')
                    v_final = ds_comp['velocityMeridional'].mean(dim='nCells')
                    plt.plot(
                        u_final,
                        z_mid_final,
                        '-',
                        color=color,
                        label=f'u {comparison_name}, {t_days:2g} days',
                    )
                    plt.plot(
                        v_final,
                        z_mid_final,
                        '--',
                        color=color,
                        label=f'v {comparison_name}, {t_days:2g} days',
                    )
                    curves_plotted += 1
                else:
                    if field_name not in ds_comp.keys():
                        if os.path.exists(f'{comparison_name}_diags.nc'):
                            ds_diags = self.open_model_dataset(
                                f'{comparison_name}.nc',
                                decode_times=True,
                            )
                            if field_name in ds_diags.keys():
                                t_arr = get_days_since_start(ds_diags)
                                t_index = np.argmin(np.abs(t_arr - t_target))
                                var_comp = ds_diags[field_name].isel(Time=t_index).mean(dim='nCells')
                            else:
                                self.logger.info(
                                    f'\t{field_name} not found; skipping plot for '
                                    f'{comparison_name}'
                                )
                                continue
                        else:
                            self.logger.info(
                                f'\t{field_name} not found; skipping plot for '
                                f'{comparison_name}'
                            )
                            continue
                    else:
                        var_comp = ds_comp[field_name].mean(dim='nCells')
                    if 'nVertLevelsP1' in var_comp.dims:
                        var_comp = var_comp.isel(nVertLevelsP1=slice(0, -1))
                    # TODO delete this line when MPAS-O bug is fixed
                    if field_name == 'RiTopOfCell':
                        var_comp[0] = np.nan
                    plt.plot(
                        var_comp,
                        z_mid_final,
                        '-',
                        color=color,
                        label=f'{comparison_name}, {t_days:2g} days',
                    )
                    curves_plotted += 1
                    # Plot initial state if available and hasn't already been
                    # plotted
                    existing_labels = [
                        lbl
                        for lbl in plt.gca().get_legend_handles_labels()[1]
                        if isinstance(lbl, str)
                    ]
                    if field_name in ds_init.keys() and \
                            'initial' not in existing_labels:
                        var_init = ds_init[field_name].mean(dim='nCells')
                        plt.plot(var_init, z_mid_init, '--k', label='initial')
                        curves_plotted += 1
            if curves_plotted == 0:
                self.logger.warn(
                    f'No data plotted for {field_name}, skipping save'
                )
                plt.close()
                continue
            plt.ylim([-100, 0])
            if field_name == 'temperature':
                plt.xlim([15, 25])
            else:
                plt.xlim(auto=True)
            plt.xlabel(f'{field_name} ({field_units})')
            plt.ylabel('z (m)')
            # Place a single legend centered below the x-axis
            fig.legend(
                loc='upper center',
                bbox_to_anchor=(0.5, -0.08),
                ncol=1,
                frameon=False,
            )
            plt.savefig(f'{field_name}.png', bbox_inches='tight')
            print(f'Plotted {field_name}')
            plt.close()
