from math import pi

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants

from polaris.mpas import area_for_field
from polaris.ocean.model import OceanIOStep
from polaris.viz import plot_horiz_field, use_mplstyle


class Analysis(OceanIOStep):
    """
    A step for analysing the output from the barotropic gyre
    test case
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
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='mesh.nc',
            target='../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../init/init.nc')
        self.add_input_file(
            filename='output.nc',
            target='../long_forward/output.nc')

    def run(self):

        ds_mesh = xr.open_dataset('mesh.nc')
        ds_init = xr.open_dataset('init.nc')
        ds = xr.open_dataset('output.nc')

        error = self.compute_error(ds_mesh, ds, variable_name='ssh')
        print(f'L2 error norm for SSH field: {error:1.2e}')

        field_mpas = ds.ssh.isel(Time=-1)
        field_exact = self.exact_solution(ds_mesh, self.config)
        ds['ssh_exact'] = field_exact
        ds['ssh_error'] = field_mpas - field_exact
        eta0 = np.max(np.abs(ds.ssh.values))
        error_range = np.max(np.abs(ds.ssh_error.values))

        use_mplstyle()
        fig, axes = plt.subplots(nrows=1, ncols=3, figsize=(10, 2))
        cell_mask = ds_init.maxLevelCell >= 1
        patches, patch_mask = plot_horiz_field(
            ds, ds_mesh, 'ssh', ax=axes[0], cmap='cmo.balance',
            t_index=ds.sizes["Time"] - 1, vmin=-eta0, vmax=eta0,
            cmap_title="SSH", cell_mask=cell_mask)
        plot_horiz_field(ds, ds_mesh, 'ssh_exact', ax=axes[1],
                         cmap='cmo.balance',
                         vmin=-eta0, vmax=eta0, cmap_title="SSH",
                         patches=patches, patch_mask=patch_mask)
        plot_horiz_field(ds, ds_mesh, 'ssh_error', ax=axes[2],
                         cmap='cmo.balance', cmap_title="dSSH",
                         vmin=-error_range, vmax=error_range,
                         patches=patches, patch_mask=patch_mask)

        axes[0].set_title('Numerical solution')
        axes[1].set_title('Analytical solution')
        axes[2].set_title('Error (Numerical - Analytical)')
        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)

    def compute_error(self, ds_mesh, ds_out, variable_name, error_type='l2'):
        """
        Compute the error for a given resolution

        Parameters
        ----------
        ds_mesh: xarray.Dataset
            the mesh dataset

        ds_out: xarray.Dataset
            the output dataset

        variable_name : str
            The variable name of which to evaluate error with respect to the
            exact solution

        zidx : int, optional
            The z index to use to slice the field given by variable name

        error_type: {'l2', 'inf'}, optional
            The type of error to compute

        Returns
        -------
        error : float
            The error of the variable given by variable_name
        """
        norm_type = {'l2': None, 'inf': np.inf}

        field_exact = self.exact_solution(ds_mesh, self.config)
        ds_out = ds_out.isel(Time=-1)
        field_mpas = ds_out[variable_name]
        diff = field_exact - field_mpas

        # Only the L2 norm is area-weighted
        if error_type == 'l2':
            area = area_for_field(ds_mesh, diff)
            field_exact = field_exact * area
            diff = diff * area
        error = np.linalg.norm(diff, ord=norm_type[error_type])

        # Normalize the error norm by the vector norm of the exact solution
        den = np.linalg.norm(field_exact, ord=norm_type[error_type])
        error = np.divide(error, den)

        return error

    def exact_solution(self, ds_mesh, config):
        """
        Exact solution to the sea surface height for the linearized Munk layer
        experiments.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Must contain the fields: `xCell`, `yCell`, ....
        """

        x = ds_mesh.xCell
        x = x - x.min()
        y = ds_mesh.yCell
        y = y - y.min()
        L_x = float(x.max() - x.min())
        L_y = float(y.max() - y.min())
        # vertical coordinate parameters
        H = config.getfloat('vertical_grid', 'bottom_depth')
        # coriolis parameters
        f_0 = config.getfloat("barotropic_gyre", "f_0")
        beta = config.getfloat("barotropic_gyre", "beta")
        # surface (wind) forcing parameters
        tau_0 = config.getfloat("barotropic_gyre", "tau_0")
        # Laplacian viscosity
        nu = config.getfloat("barotropic_gyre", "nu_2")

        # TODO get gravity and rho_sw
        rho_0 = config.getfloat("barotropic_gyre", "rho_0")
        g = constants['SHR_CONST_G']
        f = f_0 + beta * y
        delta_m = (nu / beta)**(1. / 3.)
        gamma = (np.sqrt(3.) * x) / (2. * delta_m)

        ssh = ((tau_0 / (rho_0 * g * H)) * f / beta *
               (1. - x / L_x) * pi * np.sin(pi * y / L_y) *
               (1. - np.exp(-1. * x / (2. * delta_m)) *
                (np.cos(gamma) + (1. / np.sqrt(3.)) * np.sin(gamma))))

        return ssh
