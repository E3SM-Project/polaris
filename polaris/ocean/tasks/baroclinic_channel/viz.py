import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.viz import plot_horiz_field


class Viz(Step):
    """
    A step for plotting the results of a series of baroclinic channel RPE runs
    """
    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.add_input_file(
            filename='mesh.nc',
            target='../../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../../init/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the task
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        ds_init = xr.load_dataset('init.nc')
        ds = xr.load_dataset('output.nc')
        ds['maxLevelCell'] = ds_init.maxLevelCell
        t_index = ds.sizes['Time'] - 1
        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'final_temperature.png', t_index=t_index)
        max_velocity = np.max(np.abs(ds.normalVelocity.values))
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'final_normalVelocity.png',
                         t_index=t_index,
                         vmin=-max_velocity, vmax=max_velocity,
                         cmap='cmo.balance', show_patch_edges=True)
