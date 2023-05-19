import datetime

import cmocean  # noqa: E401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.tests.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)
from polaris.viz import plot_horiz_field


class Analysis(Step):
    """
    A step for visualizing the output from the inertial gravity wave
    test case

    Attributes
    ----------
    resolutions : list of int
        The resolutions of the meshes that have been run
    """
    def __init__(self, test_case, resolutions):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.ocean.tests.inertial_gravity_wave.convergence.Convergence # noqa: E501
            The test case this step belongs to

        resolutions : list of int
            The resolutions of the meshes that have been run
        """
        super().__init__(test_case=test_case, name='analysis')
        self.resolutions = resolutions

        for resolution in resolutions:
            self.add_input_file(
                filename=f'init_{resolution}km.nc',
                target=f'../{resolution}km/initial_state/initial_state.nc')
            self.add_input_file(
                filename=f'output_{resolution}km.nc',
                target=f'../{resolution}km/forward/output.nc')

        self.add_output_file('convergence.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        config = self.config
        resolutions = self.resolutions

        section = config['inertial_gravity_wave']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        eta0 = section.getfloat('eta0')
        npx = section.getfloat('nx')
        npy = section.getfloat('ny')

        fig, axes = plt.subplots(nrows=3, ncols=3)
        rmse = []
        for i, res in enumerate(resolutions):
            init = xr.open_dataset(f'init_{res}km.nc')
            ds = xr.open_dataset(f'output_{res}km.nc')
            exact = ExactSolution(init, eta0, npx, npy, lx, ly)

            t0 = datetime.datetime.strptime(ds.xtime.values[0].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            tf = datetime.datetime.strptime(ds.xtime.values[-1].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            t = (tf - t0).total_seconds()
            rmse.append(np.sqrt(np.mean((ds.ssh - exact.ssh(t))**2)))
            ds['ssh_exact'] = exact.ssh(t)
            ds['ssh_error'] = ds.ssh - exact.ssh(t)
            error_range = np.max(np.abs(ds.ssh_error.values))
            plot_horiz_field(ds, init, 'ssh', ax=axes[i, 0],
                             cmap='cmo.balance')
            plot_horiz_field(ds, init, 'ssh_exact', ax=axes[i, 1],
                             cmap='cmo.balance')
            plot_horiz_field(ds, init, 'ssh_error', ax=axes[i, 2],
                             cmap='cmo.balance',
                             vmin=-error_range, vmax=error_range)

        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.loglog(resolutions, rmse)
        fig.savefig('convergence.png', bbox_inches='tight', pad_inches=0.1)
