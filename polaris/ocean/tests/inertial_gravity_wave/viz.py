import datetime

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.tests.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)
from polaris.viz import plot_horiz_field


class Viz(Step):
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
        super().__init__(test_case=test_case, name='viz')
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
        nres = len(resolutions)

        section = config['inertial_gravity_wave']
        eta0 = section.getfloat('eta0')

        fig, axes = plt.subplots(nrows=nres, ncols=3, figsize=(12, 2 * nres))
        rmse = []
        for i, res in enumerate(resolutions):
            init = xr.open_dataset(f'init_{res}km.nc')
            ds = xr.open_dataset(f'output_{res}km.nc')
            exact = ExactSolution(init, config)

            t0 = datetime.datetime.strptime(ds.xtime.values[0].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            tf = datetime.datetime.strptime(ds.xtime.values[-1].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            t = (tf - t0).total_seconds()
            ssh_model = ds.ssh.values[-1, :]
            rmse.append(np.sqrt(np.mean((ssh_model - exact.ssh(t).values)**2)))

            # Comparison plots
            ds['ssh_exact'] = exact.ssh(t)
            ds['ssh_error'] = ssh_model - exact.ssh(t)
            if i == 0:
                error_range = np.max(np.abs(ds.ssh_error.values))

            plot_horiz_field(ds, init, 'ssh', ax=axes[i, 0],
                             cmap='cmo.balance', t_index=ds.sizes["Time"] - 1,
                             vmin=-eta0, vmax=eta0)
            plot_horiz_field(ds, init, 'ssh_exact', ax=axes[i, 1],
                             cmap='cmo.balance',
                             vmin=-eta0, vmax=eta0)
            plot_horiz_field(ds, init, 'ssh_error', ax=axes[i, 2],
                             cmap='cmo.balance',
                             vmin=-error_range, vmax=error_range)

        axes[0, 0].set_title('Numerical')
        axes[0, 1].set_title('Exact')
        axes[0, 2].set_title('Error')

        pad = 5
        for ax, res in zip(axes[:, 0], resolutions):
            ax.annotate(f'{res}km', xy=(0, 0.5),
                        xytext=(-ax.yaxis.labelpad - pad, 0),
                        xycoords=ax.yaxis.label, textcoords='offset points',
                        size='large', ha='right', va='center')

        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)

        # Convergence polts
        fig = plt.figure()
        ax = fig.add_subplot(111)
        p = np.polyfit(np.log10(resolutions), np.log10(rmse), 1)
        conv = np.round(p[0], 3)
        ax.loglog(resolutions, rmse, '-ok', label=f'numerical (order={conv})')

        c = rmse[0] * 1.5 / resolutions[0]
        order1 = c * np.power(resolutions, 1)
        c = rmse[0] * 1.5 / resolutions[0]**2
        order2 = c * np.power(resolutions, 2)

        ax.loglog(resolutions, order1, '--k', label='first order', alpha=0.3)
        ax.loglog(resolutions, order2, 'k', label='second order', alpha=0.3)
        ax.set_xlabel('resolution (km)')
        ax.set_ylabel('RMS error (m)')
        ax.set_title('Error Convergence')
        ax.legend(loc='lower right')
        fig.savefig('convergence.png', bbox_inches='tight', pad_inches=0.1)
