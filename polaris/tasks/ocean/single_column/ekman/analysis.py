from math import pi

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.mpas import area_for_field
from polaris.viz import use_mplstyle


class Analysis(Step):
    """
    A step for comparing the velocity profile to an analytic solution
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
            filename='init.nc', target='../forward/initial_state.nc'
        )
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
        )

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        use_mplstyle()

        config = self.config
        f = config.getfloat('single_column', 'coriolis_parameter')
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        tau_x = config.getfloat('single_column_forcing', 'wind_stress_zonal')
        nu = config.getfloat('single_column_ekman', 'vertical_viscosity')
        tol = config.getfloat('single_column_ekman', 'L2_error_norm_max')

        ds_mesh = xr.load_dataset('init.nc')
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
        normal_velocity_exact = u * np.cos(ds_mesh.angleEdge) + v * np.sin(
            ds_mesh.angleEdge
        )
        diff = ds.normalVelocity - normal_velocity_exact
        z_slice = slice(0, zidx)
        diff = diff.isel(nVertLevels=z_slice)
        normal_velocity_exact = normal_velocity_exact.isel(nVertLevels=z_slice)
        error = _compute_error(ds_mesh, diff, normal_velocity_exact)

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

        # Write out some information about the error
        logger.info(f'L2 norm of normal velocity: {error:1.1e}')

        # Test case fails if the L2 norm exceeds some value
        if error > tol:
            logger.error(
                'error: L2 norm of normal velocity '
                f'{error:1.1e} exceeds tolerance {tol:1.1e}'
            )
            raise ValueError('L2 norm exceeds tolerance')


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


def _compute_error(ds_mesh, diff, field_exact):
    # Compute the area-weighted L2 norm
    area = area_for_field(ds_mesh, diff)
    field_exact = field_exact * area
    diff = diff * area
    error = np.linalg.norm(diff, ord=2)

    # Normalize the error norm by the vector norm of the exact solution
    den = np.linalg.norm(field_exact, ord=2)
    error = np.divide(error, den)
    return error
