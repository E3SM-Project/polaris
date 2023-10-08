import datetime

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)
from polaris.viz import plot_horiz_field, use_mplstyle


class Viz(Step):
    """
    A step for visualizing the output from the inertial gravity wave
    test case

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run
    """
    def __init__(self, component, resolutions, taskdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        taskdir : str
            The subdirectory that the task belongs to
        """
        super().__init__(component=component, name='viz', indir=taskdir)
        self.resolutions = resolutions

        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            self.add_input_file(
                filename=f'mesh_{mesh_name}.nc',
                target=f'../init/{mesh_name}/culled_mesh.nc')
            self.add_input_file(
                filename=f'init_{mesh_name}.nc',
                target=f'../init/{mesh_name}/initial_state.nc')
            self.add_input_file(
                filename=f'output_{mesh_name}.nc',
                target=f'../forward/{mesh_name}/output.nc')

        self.add_output_file('convergence.png')
        self.add_output_file('comparison.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        config = self.config
        resolutions = self.resolutions
        nres = len(resolutions)

        section = config['inertial_gravity_wave']
        eta0 = section.getfloat('ssh_amplitude')

        use_mplstyle()
        fig, axes = plt.subplots(nrows=nres, ncols=3, figsize=(12, 2 * nres))
        rmse = []
        error_range = None
        for i, res in enumerate(resolutions):
            mesh_name = resolution_to_subdir(res)
            ds_mesh = xr.open_dataset(f'mesh_{mesh_name}.nc')
            ds_init = xr.open_dataset(f'init_{mesh_name}.nc')
            ds = xr.open_dataset(f'output_{mesh_name}.nc')
            ds['maxLevelCell'] = ds_init.maxLevelCell
            exact = ExactSolution(ds_init, config)

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
            if error_range is None:
                error_range = np.max(np.abs(ds.ssh_error.values))

            plot_horiz_field(ds, ds_mesh, 'ssh', ax=axes[i, 0],
                             cmap='cmo.balance', t_index=ds.sizes["Time"] - 1,
                             vmin=-eta0, vmax=eta0, cmap_title="SSH (m)")
            plot_horiz_field(ds, ds_mesh, 'ssh_exact', ax=axes[i, 1],
                             cmap='cmo.balance',
                             vmin=-eta0, vmax=eta0, cmap_title="SSH (m)")
            plot_horiz_field(ds, ds_mesh, 'ssh_error', ax=axes[i, 2],
                             cmap='cmo.balance',
                             cmap_title=r"$\Delta$ SSH (m)",
                             vmin=-error_range, vmax=error_range)

        axes[0, 0].set_title('Numerical solution')
        axes[0, 1].set_title('Analytical solution')
        axes[0, 2].set_title('Error (Numerical - Analytical)')

        pad = 5
        for ax, res in zip(axes[:, 0], resolutions):
            ax.annotate(f'{res}km', xy=(0, 0.5),
                        xytext=(-ax.yaxis.labelpad - pad, 0),
                        xycoords=ax.yaxis.label, textcoords='offset points',
                        size='large', ha='right', va='center')

        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)

        # Convergence plots
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
        ax.invert_xaxis()
        ax.set_title('Error Convergence')
        ax.legend(loc='lower left')
        fig.savefig('convergence.png', bbox_inches='tight', pad_inches=0.1)
