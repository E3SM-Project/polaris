import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.time import get_days_since_start
from polaris.ocean.vertical.diagnostics import depth_from_thickness
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
        self.comparisons = comparisons if comparisons else dict()
        self.add_input_file(
            filename='initial_state.nc', target='../init/initial_state.nc'
        )
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
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

        ds = self.open_model_dataset('output.nc', decode_times=False)
        t_arr = get_days_since_start(ds)
        t_index = np.argmin(np.abs(t_arr - 1.0))  # index nearest 1 day
        t_days = float(t_arr[t_index])
        ds_final = ds.isel(Time=t_index)

        # Plot temperature and salinity profiles
        title = f'final time = {t_days:2.1g} days'
        print(f't_index = {t_index}, t_days = {t_days}')
        fields = {'temperature': 'degC', 'salinity': 'PSU'}
        if ideal_age:
            # Include age tracer
            fields['iAge'] = 'seconds'
        z_mid_init = depth_from_thickness(ds_init).mean(dim='nCells')
        z_mid_final = depth_from_thickness(ds_final).mean(dim='nCells')
        for field_name, field_units in fields.items():
            if field_name not in ds_init.keys():
                raise ValueError(
                    f'{field_name} not present in initial_state.nc'
                )
            if field_name not in ds_final.keys():
                raise ValueError(f'{field_name} not present in output.nc')
            var_init = ds_init[field_name].mean(dim='nCells')
            var_final = ds_final[field_name].mean(dim='nCells')
            print('Size of variables to plot')
            print(
                f'Change of {field_name} at the surface: '
                f'{var_final.values[0] - var_init.values[0]}'
            )
            print(
                f'Change of {field_name} at the bottom: '
                f'{var_final.values[-1] - var_init.values[-1]}'
            )

            plt.figure(figsize=(3, 5))
            ax = plt.subplot(111)
            ax.plot(var_init, z_mid_init, '--k', label='initial')
            ax.plot(var_final, z_mid_final, '-k', label='final')
            for comparison_name, _ in self.comparisons.items():
                ds_comp = self.open_model_dataset(
                    f'{comparison_name}.nc', decode_times=False
                )
                t_arr = get_days_since_start(ds_comp)
                t_index = np.argmin(np.abs(t_arr - 1.0))  # index nearest 1 day
                t_days = float(t_arr[t_index])
                print(f't_index = {t_index}, t_days = {t_days}')
                ds_comp = ds_comp.isel(Time=t_index)
                if field_name not in ds_comp.keys():
                    raise ValueError(
                        f'{field_name} not present in {comparison_name}.nc'
                    )
                var_comp = ds_comp[field_name].mean(dim='nCells')
                ax.plot(var_comp, z_mid_final, '-r', label=comparison_name)
            ax.set_xlabel(f'{field_name} ({field_units})')
            ax.set_ylabel('z (m)')
            # ax.legend()
            plt.title(title)
            plt.tight_layout(pad=0.5)
            plt.savefig(f'{field_name}.png')
            plt.close()

        # Plot velocity profiles
        if 'velocityZonal' and 'velocityMeridional' in ds.keys():
            u = ds['velocityZonal'].mean(dim='nCells')
            v = ds['velocityMeridional'].mean(dim='nCells')
            u_final = u.isel(Time=t_index)
            v_final = v.isel(Time=t_index)
            plt.figure(figsize=(3, 5))
            ax = plt.subplot(111)
            ax.plot(u_final, z_mid_final, '-k', label='u')
            ax.plot(v_final, z_mid_final, '-b', label='v')
            ax.set_xlabel('Velocity (m/s)')
            ax.set_ylabel('z (m)')
            ax.legend()
            plt.title(title)
            plt.tight_layout(pad=0.5)
            plt.savefig('velocity.png')
            plt.close()
