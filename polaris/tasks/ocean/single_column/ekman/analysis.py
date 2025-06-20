from math import pi

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.viz import use_mplstyle


class Analysis(Step):
    """
    A step for plotting the results of a single-column test
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
        )

    def run(self):
        """
        Run this step of the test case
        """
        use_mplstyle()

        config = self.config
        f = config.getfloat('single_column', 'coriolis_parameter')
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        tau_x = config.getfloat('single_column_forcing', 'wind_stress_zonal')
        nu = config.getfloat('single_column_ekman', 'vertical_viscosity')
        ds = xr.load_dataset('output.nc')
        t_index = ds.sizes['Time'] - 1
        t = ds.daysSinceStartOfSim[t_index]
        t_days = t.values.astype('timedelta64[D]')
        ds = ds.isel(Time=t_index)
        title = f'final time = {t_days / np.timedelta64(1, "D")} days'
        z_mid = ds.zMid.mean(dim='nCells').values
        rho_0 = ds['density'].mean(dim='nCells').isel(nVertLevels=0).values
        u = ds['velocityZonal'].mean(dim='nCells')
        v = ds['velocityMeridional'].mean(dim='nCells')
        z_max = bottom_depth / 3.0
        zidx = np.argmin(np.abs(z_mid + z_max))
        u_exact, v_exact = _exact_solution(
            z_mid[:zidx], nu, f, tau_x=tau_x / rho_0
        )

        plt.figure(figsize=(3, 5))
        ax = plt.subplot(111)
        ax.plot(u_exact, z_mid[:zidx], '-k', label='u')
        ax.plot(v_exact, z_mid[:zidx], '-b', label='v')
        ax.plot(u[:zidx], z_mid[:zidx], '.k')
        ax.plot(v[:zidx], z_mid[:zidx], '.b')
        ax.set_xlabel('Velocity (m/s)')
        ax.set_ylabel('z (m)')
        ax.legend()
        plt.title(title)
        plt.tight_layout(pad=0.5)
        plt.savefig('velocity_comparison.png')
        plt.close()


def _exact_solution(depth, nu, f, u_g=0.0, v_g=0.0, tau_x=0.0, tau_y=0.0):
    """
    depth : float, vector
        negative downward distance at which to solve for the exact solution

    nu : float
        kinematic vertical viscosity (eddy diffusivity)

    f : float
        Coriolis parameter (1/s)

    u_g : float, optional
        geostrophic velocity in zonal direction

    v_g : float, optional
        geostrophic velocity in meridional direction

    tau_x : float, optional
        kinematic stress in zonal direction (tau/rho)

    tau_y : float, optional
        kinematic stress in meridional direction (tau/rho)
    """
    ekman_depth = (2 * nu / f) ** 0.5
    u_0 = 2**0.5 * tau_x / (ekman_depth * f)
    v_0 = 2**0.5 * tau_y / (ekman_depth * f)
    z = depth / ekman_depth
    u = u_g + np.exp(z) * (
        u_0 * np.cos(z - pi / 4.0) - v_0 * np.sin(z - pi / 4.0)
    )
    v = v_g + np.exp(z) * (
        u_0 * np.sin(z - pi / 4.0) + v_0 * np.cos(z - pi / 4.0)
    )
    return u, v
