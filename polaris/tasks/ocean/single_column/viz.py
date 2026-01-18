import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.time import get_days_since_start
from polaris.viz import use_mplstyle


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
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.ideal_age = ideal_age
        self.comparisons = (
            dict(comparisons)
            if comparisons
            else {'forward': '../forward/output.nc'}
        )
        self.add_input_file(
            filename='initial_state.nc', target='../init/initial_state.nc'
        )
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        use_mplstyle()
        ideal_age = self.ideal_age

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

        # Plot temperature and salinity profiles
        fields = {'temperature': 'degC', 'salinity': 'PSU'}
        if ideal_age:
            # Include age tracer
            fields['iAge'] = 'seconds'
        for field_name, field_units in fields.items():
            if field_name not in ds_init.keys():
                raise ValueError(
                    f'{field_name} not present in initial_state.nc'
                )
            var_init = ds_init[field_name].mean(dim='nCells')

            fig = plt.figure(figsize=(3, 5))
            colors = ['b', 'r', 'darkgreen']
            plt.plot(var_init, z_mid_init, '--k', label='initial')
            for comparison_name, color in zip(
                self.comparisons.keys(), colors, strict=False
            ):
                ds_comp = self.open_model_dataset(
                    f'{comparison_name}.nc', decode_times=False
                )
                t_arr = get_days_since_start(ds_comp)
                t_index = np.argmin(np.abs(t_arr - t_target))
                t_days = float(t_arr[t_index])
                ds_comp = ds_comp.isel(Time=t_index)
                if field_name not in ds_comp.keys():
                    raise ValueError(
                        f'{field_name} not present in {comparison_name}.nc'
                    )
                var_comp = ds_comp[field_name].mean(dim='nCells')
                z_mid_final = ds_comp['zMid'].mean(dim='nCells')
                plt.plot(
                    var_comp,
                    z_mid_final,
                    '-',
                    color=color,
                    label=comparison_name,
                )
            title = f'final time = {t_days:2.1g} days'
            plt.xlabel(f'{field_name} ({field_units})')
            plt.ylabel('z (m)')
            fig.legend(loc='outside lower right')
            plt.title(title)
            plt.tight_layout(pad=0.5)
            plt.savefig(f'{field_name}.png')
            plt.close()

        # Plot velocity profiles
        plt.figure(figsize=(3, 5))
        ax = plt.subplot(111)
        for comparison_name, color in zip(
            self.comparisons.keys(), colors, strict=False
        ):
            ds_comp = self.open_model_dataset(
                f'{comparison_name}.nc', decode_times=False
            )
            t_arr = get_days_since_start(ds_comp)
            t_index = np.argmin(np.abs(t_arr - t_target))
            t_days = float(t_arr[t_index])
            print(f't_index = {t_index}, t_days = {t_days}')
            ds_comp = ds_comp.isel(Time=t_index)
            z_mid_final = ds_comp['zMid'].mean(dim='nCells')
            if 'velocityZonal' and 'velocityMeridional' in ds_comp.keys():
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
