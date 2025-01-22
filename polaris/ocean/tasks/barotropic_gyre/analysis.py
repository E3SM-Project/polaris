from math import pi

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import mosaic
import numpy as np
import xarray as xr
from mpas_tools.ocean import compute_barotropic_streamfunction

from polaris.mpas import area_for_field
from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class Analysis(OceanIOStep):
    """
    A step for analysing the output from the barotropic gyre
    test case
    """

    def __init__(self, component, indir, boundary_condition='free slip'):
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
        self.boundary_condition = boundary_condition

    def run(self):

        ds_mesh = xr.open_dataset('mesh.nc')
        ds_init = xr.open_dataset('init.nc')
        ds = xr.open_dataset('output.nc')

        field_mpas = compute_barotropic_streamfunction(
            ds_init.isel(Time=0), ds, prefix='', time_index=-1)
        field_exact = self.exact_solution(
            ds_mesh, self.config, loc='Vertex',
            boundary_condition=self.boundary_condition)

        ds['psi'] = field_mpas
        ds['psi_exact'] = field_exact
        ds['psi_error'] = field_mpas - field_exact

        error = self.compute_error(ds_mesh, ds, variable_name='psi',
                                   boundary_condition=self.boundary_condition)
        print(f'L2 error norm for {self.boundary_condition} bsf: {error:1.2e}')

        descriptor = mosaic.Descriptor(ds_mesh)

        use_mplstyle()
        pad = 20
        fig, axes = plt.subplots(nrows=1, ncols=3, figsize=(12, 2))
        x0 = float(ds_mesh.xEdge.min())
        y0 = float(ds_mesh.yEdge.min())

        # offset coordinates
        descriptor.vertex_patches[..., 0] -= x0
        descriptor.vertex_patches[..., 1] -= y0
        # convert to km
        descriptor.vertex_patches *= 1.e-3

        eta0 = max(np.max(np.abs(field_exact.values)),
                   np.max(np.abs(field_mpas.values)))

        s = mosaic.polypcolor(axes[0], descriptor, field_mpas, vmin=-eta0,
                              vmax=eta0, cmap='cmo.balance', antialiased=False)
        cbar = fig.colorbar(s, ax=axes[0])
        cbar.ax.set_title(r'$\psi$')
        s = mosaic.polypcolor(axes[1], descriptor, field_exact, vmin=-eta0,
                              vmax=eta0, cmap='cmo.balance', antialiased=False)
        cbar = fig.colorbar(s, ax=axes[1])
        cbar.ax.set_title(r'$\psi$')
        eta0 = np.max(np.abs(field_mpas.values - field_exact.values))
        s = mosaic.polypcolor(axes[2], descriptor, field_mpas - field_exact,
                              vmin=-eta0, vmax=eta0, cmap='cmo.balance',
                              antialiased=False)
        cbar = fig.colorbar(s, ax=axes[2])
        cbar.ax.set_title(r'$d\psi$')
        axes[0].set_title('Numerical solution', pad=pad)
        axes[0].set_ylabel('y (km)')
        axes[0].set_xlabel('x (km)')
        axes[1].set_title('Analytical solution', pad=pad)
        axes[1].set_xlabel('x (km)')
        axes[2].set_title('Error (Numerical - Analytical)', pad=pad)
        axes[2].set_xlabel('x (km)')

        xmin = descriptor.vertex_patches[..., 0].min()
        xmax = descriptor.vertex_patches[..., 0].max()
        ymin = descriptor.vertex_patches[..., 1].min()
        ymax = descriptor.vertex_patches[..., 1].max()
        for ax in axes:
            ax.set_xlim(xmin, xmax)
            ax.set_ylim(ymin, ymax)
            ax.set_aspect('equal')
        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)

    def compute_error(self, ds_mesh, ds_out, variable_name, error_type='l2',
                      loc='Vertex', boundary_condition='free slip'):
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

        field_exact = self.exact_solution(
            ds_mesh, self.config, loc=loc,
            boundary_condition=self.boundary_condition)
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

    def exact_solution(self, ds_mesh, config, loc='Cell',
                       boundary_condition='free slip'):
        """
        Exact solution to the sea surface height for the linearized Munk layer
        experiments.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Must contain the fields: f'x{loc}', f'y{loc}'
        """

        x = ds_mesh[f'x{loc}']
        x = x - ds_mesh.xEdge.min()
        y = ds_mesh[f'y{loc}']
        y = y - ds_mesh.yEdge.min()
        L_x = float(x.max() - x.min())
        L_y = float(y.max() - y.min())

        # df/dy where f is coriolis parameter
        beta = config.getfloat("barotropic_gyre", "beta")
        # Laplacian viscosity
        nu = config.getfloat("barotropic_gyre", "nu_2")

        # Compute some non-dimensional numbers
        delta_m = (nu / (beta * L_y**3.))**(1. / 3.)
        gamma = (np.sqrt(3.) * x) / (2. * delta_m * L_x)

        if boundary_condition == 'no slip':
            psi = (pi * np.sin(pi * y / L_y) *
                   (1. - (x / L_x) -
                    np.exp(-x / (2. * delta_m * L_x)) *
                    (np.cos(gamma) +
                     ((1. - 2 * delta_m) / np.sqrt(3.)) * np.sin(gamma)) +
                    delta_m * np.exp(((x / L_x) - 1) / delta_m)))

        elif boundary_condition == 'free slip':
            psi = (pi * (1. - x / L_x) * np.sin(pi * y / L_y) *
                   (1. -
                    np.exp(-x / (2. * delta_m * L_x)) *
                    (np.cos(gamma) + (1. / np.sqrt(3.)) * np.sin(gamma))))
        return psi
