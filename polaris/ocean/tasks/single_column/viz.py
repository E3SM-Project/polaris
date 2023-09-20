import sys
from typing import TYPE_CHECKING  # noqa: F401

if TYPE_CHECKING or sys.version_info >= (3, 9, 0):
    import importlib.resources as imp_res  # noqa: F401
else:
    # python <= 3.8
    import importlib_resources as imp_res  # noqa: F401

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step


class Viz(Step):
    """
    A step for plotting the results of a single-column test
    """
    def __init__(self, component, indir, ideal_age=False):
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
        self.add_input_file(
            filename='initial_state.nc',
            target='../init/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the test case
        """
        style_filename = str(
            imp_res.files('polaris.viz') / 'polaris.mplstyle')
        plt.style.use(style_filename)
        ideal_age = self.ideal_age
        ds = xr.load_dataset('output.nc')
        t_index = ds.sizes['Time'] - 1
        t = ds.daysSinceStartOfSim[t_index]
        t_days = t.values.astype('timedelta64[D]')
        title = f'final time = {t_days / np.timedelta64(1, "D")} days'
        fields = {'temperature': 'degC',
                  'salinity': 'PSU'}
        if ideal_age:
            fields['iAge'] = 'seconds'
        z_mid = ds['zMid'].mean(dim='nCells')
        z_mid_init = z_mid.isel(Time=0)
        z_mid_final = z_mid.isel(Time=t_index)
        for field_name, field_units in fields.items():
            if field_name not in ds.keys():
                raise ValueError(f'{field_name} not present in output.nc')
            var = ds[field_name].mean(dim='nCells')
            var_init = var.isel(Time=0)
            var_final = var.isel(Time=t_index)
            plt.figure(figsize=(3, 5))
            ax = plt.subplot(111)
            ax.plot(var_init, z_mid_init, '--k', label='initial')
            ax.plot(var_final, z_mid_final, '-k', label='final')
            ax.set_xlabel(f'{field_name} ({field_units})')
            ax.set_ylabel('z (m)')
            ax.legend()
            plt.title(title)
            plt.tight_layout(pad=0.5)
            plt.savefig(f'{field_name}.png')
            plt.close()
