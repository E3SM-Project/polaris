import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.viz import plot_horiz_field


class Viz(Step):
    """
    A step for plotting the results of a series of RPE runs in the baroclinic
    channel test group
    """
    def __init__(self, test_case):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to
        """
        super().__init__(test_case=test_case, name='viz')
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
        ds_mesh = xr.load_dataset('initial_state.nc')
        ds = xr.load_dataset('output.nc')
        t_index = ds.sizes['Time'] - 1
        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'final_temperature.png', t_index=t_index)
        max_velocity = np.max(np.abs(ds.normalVelocity.values))
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'final_normalVelocity.png',
                         t_index=t_index,
                         vmin=-max_velocity, vmax=max_velocity,
                         cmap='cmo.balance', show_patch_edges=True)
