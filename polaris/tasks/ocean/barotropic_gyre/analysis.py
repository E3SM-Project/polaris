from math import pi

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import mosaic
import numpy as np
from matplotlib import colors as mcolors
from mpas_tools.ocean import compute_barotropic_streamfunction

from polaris.mpas import area_for_field
from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class Analysis(OceanIOStep):
    """
    A step for analyzing the output from the barotropic gyre test case.

    Attributes
    ----------
    boundary_condition : str
        The type of boundary condition to use ('free-slip' or 'no-slip').

    test_name : str
        The name of the test case (e.g., 'munk').
    """

    def __init__(
        self,
        component,
        indir,
        test_name='munk',
        boundary_condition='free-slip',
    ):
        """
        Create the analysis step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        indir : str
            The directory the step is in, to which ``name`` will be appended.

        test_name : str, optional
            The name of the test case (default is 'munk').

        boundary_condition : str, optional
            The type of boundary condition to use (default is 'free-slip').
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='mesh.nc', target='../init/culled_mesh.nc'
        )
        self.add_input_file(filename='init.nc', target='../init/init.nc')
        self.add_input_file(
            filename='output.nc', target='../long_forward/output.nc'
        )
        self.boundary_condition = boundary_condition
        self.test_name = test_name

    def run(self):
        logger = self.logger
        ds_mesh = self.open_model_dataset('mesh.nc')
        ds_init = self.open_model_dataset('init.nc')
        ds = self.open_model_dataset('output.nc')

        field_mpas = compute_barotropic_streamfunction(
            ds_init.isel(Time=0), ds, prefix='', time_index=-1
        )
        x_maxpsi = ds_mesh.xVertex.isel(nVertices=np.argmax(field_mpas.values))
        logger.info(f'Streamfunction reaches maximum at x = {x_maxpsi.values}')
        field_exact = self.exact_solution(
            ds_mesh,
            self.config,
            loc='Vertex',
            boundary_condition=self.boundary_condition,
        )

        ds['psi'] = field_mpas
        ds['psi_exact'] = field_exact
        ds['psi_error'] = field_mpas - field_exact

        error = self.compute_error(
            ds_mesh,
            ds,
            variable_name='psi',
            boundary_condition=self.boundary_condition,
        )
        logger.info(
            f'L2 error norm for {self.boundary_condition} bsf: {error:1.2e}'
        )

        descriptor = mosaic.Descriptor(ds_mesh)

        use_mplstyle()
        pad = 20
        x0 = ds_mesh.xEdge.min().values
        y0 = ds_mesh.yEdge.min().values

        # offset coordinates
        descriptor.vertex_patches[..., 0] -= x0
        descriptor.vertex_patches[..., 1] -= y0
        # convert to km
        descriptor.vertex_patches *= 1.0e-3

        fig, axes = plt.subplots(nrows=1, ncols=3, figsize=(12, 2))

        eta0 = max(
            np.max(np.abs(field_exact.values)),
            np.max(np.abs(field_mpas.values)),
        )

        bounds = np.linspace(-eta0, eta0, 21)
        norm = mcolors.BoundaryNorm(bounds, cmocean.cm.amp.N)
        s = mosaic.polypcolor(
            axes[0],
            descriptor,
            field_mpas,
            cmap='cmo.balance',
            norm=norm,
            antialiased=False,
        )
        cbar = fig.colorbar(s, ax=axes[0])
        cbar.ax.set_title(r'$\psi$')
        s = mosaic.polypcolor(
            axes[1],
            descriptor,
            field_exact,
            cmap='cmo.balance',
            norm=norm,
            antialiased=False,
        )
        cbar = fig.colorbar(s, ax=axes[1])
        cbar.ax.set_title(r'$\psi$')

        eta0 = np.max(np.abs(field_mpas.values - field_exact.values))
        bounds = np.linspace(-eta0, eta0, 11)
        norm = mcolors.BoundaryNorm(bounds, cmocean.cm.balance.N)
        s = mosaic.polypcolor(
            axes[2],
            descriptor,
            field_mpas - field_exact,
            cmap='cmo.balance',
            norm=norm,
            antialiased=False,
        )
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

    def compute_error(
        self,
        ds_mesh,
        ds_out,
        variable_name,
        error_type='l2',
        loc='Vertex',
        boundary_condition='free slip',
    ):
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
            ds_mesh,
            self.config,
            loc=loc,
            boundary_condition=self.boundary_condition,
        )
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

    def exact_solution(
        self, ds_mesh, config, loc='Cell', boundary_condition='free slip'
    ):
        """
        Exact solution to the barotropic streamfunction for the linearized Munk
        layer experiments.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            The mesh dataset. Must contain the fields: f'x{loc}', f'y{loc}'.

        config : polaris.config.PolarisConfigParser
            The configuration options for the test case.

        loc : str, optional
            The location type ('Cell', 'Vertex', etc.) for which to compute
            the solution.

        boundary_condition : str, optional
            The type of boundary condition to use ('free-slip' or 'no-slip').
        """

        logger = self.logger
        test_name = self.test_name
        boundary_condition = self.boundary_condition
        x = ds_mesh[f'x{loc}']
        x = x - ds_mesh.xEdge.min()
        y = ds_mesh[f'y{loc}']
        y = y - ds_mesh.yEdge.min()
        L_x = float(x.max() - x.min())
        L_y = float(y.max() - y.min())

        # df/dy where f is coriolis parameter
        beta = config.getfloat('barotropic_gyre', 'beta')
        # Laplacian viscosity
        nu = config.getfloat(
            f'barotropic_gyre_{test_name}_{boundary_condition}', 'nu_2'
        )

        # Compute some non-dimensional numbers
        delta_m = (nu / (beta * L_y**3.0)) ** (1.0 / 3.0)
        gamma = (np.sqrt(3.0) * x) / (2.0 * delta_m * L_x)
        x_maxpsi = 2 * delta_m / np.sqrt(3.0)
        logger.info(f'Streamfunction should reach maximum at x = {x_maxpsi}')

        if boundary_condition == 'no-slip':
            psi = (
                pi
                * np.sin(pi * y / L_y)
                * (
                    1.0
                    - (x / L_x)
                    - np.exp(-x / (2.0 * delta_m * L_x))
                    * (
                        np.cos(gamma)
                        + ((1.0 - 2 * delta_m) / np.sqrt(3.0)) * np.sin(gamma)
                    )
                    + delta_m * np.exp(((x / L_x) - 1) / delta_m)
                )
            )

        elif boundary_condition == 'free-slip':
            psi = (
                pi
                * np.sin(pi * (y / L_y))
                * (
                    (1.0 - (x / L_x) - delta_m)
                    + (np.exp((-(x / L_x)) / (2.0 * delta_m)))
                    * (
                        (-2 / 3) * (1 - delta_m) * np.cos(gamma - (pi / 6))
                        + ((2.0 / np.sqrt(3.0)) * np.sin(gamma))
                    )
                    + delta_m * np.exp((((x / L_x) - 1) / delta_m))
                )
            )
        return psi
