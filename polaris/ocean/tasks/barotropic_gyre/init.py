import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord
from polaris.viz import plot_horiz_field


class Init(Step):
    """
    A step for creating a mesh and initial condition for baroclinic channel
    tasks

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """
    def __init__(self, component, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to
        """
        super().__init__(component=component, name='init', indir=subdir)

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info']:
            self.add_output_file(file)
        self.add_output_file('initial_state.nc',
                             validate_vars=['layerThickness'])

    def run(self):
        """Create the at rest inital condition for the barotropic gyre testcase
        """
        config = self.config
        logger = self.logger
        # domain parameters
        lx = config.getfloat("barotropic_gyre", "lx")
        ly = config.getfloat("barotropic_gyre", "ly")
        resolution = config.getfloat("barotropic_gyre", "resolution")

        # convert cell spacing to meters
        dc = resolution * 1e3

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        # vertical coordinate parameters
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        # coriolis parameters
        f_0 = config.getfloat("barotropic_gyre", "f_0")
        beta = config.getfloat("barotropic_gyre", "beta")
        # surface (wind) forcing parameters
        tau_0 = config.getfloat("barotropic_gyre", "tau_0")
        # horizontal momentum diffusion parameters
        nu_2 = config.getfloat("barotropic_gyre", "nu_2")

        # calculate the boundary layer thickness for specified parameters
        M = (np.pi * 2) / np.sqrt(3) * (nu_2 / beta)**(1. / 3.)

        # ensure the boundary layer is at least 3 gridcells wide
        if M <= 3. * resolution:
            raise ValueError("resolution is too coarse to properly resolve the"
                             "the boundary (i.e. Munk) layer")

        # create a copy of the culled mesh to place the IC's into
        ds = ds_mesh.copy()

        # set the ssh initial condition to zero
        ds["ssh"] = xr.zeros_like(ds.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds.xCell)

        # use polaris framework functions to initialize the vertical coordinate
        init_vertical_coord(config, ds)

        # set the coriolis values
        for loc in ["Cell", "Edge", "Vertex"]:
            ds[f"f{loc}"] = f_0 + beta * ds[f"y{loc}"]

        # set the initial condition for normalVelocity
        ds["normalVelocity"] = xr.zeros_like(ds.xEdge).expand_dims(
            ["Time", "nVertLevels"],
            axis=[0, -1])

        # write the initial condition file
        write_netcdf(ds_mesh, 'initial_state.nc')

        # set the wind stress forcing
        ds_forcing = ds_mesh.copy()
        # Convert from km to m
        ly = ly * 1e3
        ds_forcing["windStressZonal"] = \
            -tau_0 * np.cos(np.pi * (ds.yCell - ds.yCell.min()) / ly)
        ds_forcing["windStressMeridional"] = xr.zeros_like(ds.xCell)
        write_netcdf(ds_forcing, 'forcing.nc')

        cell_mask = ds.maxLevelCell >= 1

        plot_horiz_field(ds_forcing, ds_mesh, 'windStressZonal',
                         'forcing_wind_stress_zonal.png', cmap='cmo.balance',
                         show_patch_edges=True, cell_mask=cell_mask,
                         vmin=-0.1, vmax=0.1)


def exact_ssh_solution(
        ds, tau_0=0.1, rho=1.e3, g=9.81, nu_2=4.e2, beta=1e-11, f_0=1e-4):
    """
    Exact solution to the sea surface height for the linearized Munk layer
    experiments.

    Parameters
    ----------
    ds : xarray.Dataset
        Must contain the fields: `xCell`, `yCell`, ....
    tau_0 : Float
        .... [N m-2]
    rho : Float
        Constant ocean density [kg m-3]
    g : Float
        Gravitational acceleration constant [m s-2]
    nu_2 : Float
        Viscosity [m2 s-1]
    beta : Float
        ... [s-1 m-1]
    f_0 : Float
        ... [s-1]
    """

    xCell = ds.xCell
    yCell = ds.yCell
    L_x = float(xCell.max() - xCell.min())
    L_y = float(yCell.max() - yCell.min())
    layerThickness = ds.restingThickness.squeeze()

    pi = np.pi
    sqrt3 = np.sqrt(3)
    delta_m = (nu_2 / beta)**(1. / 3.)
    gamma = (sqrt3 * ds.xCell) / (2. * delta_m)

    ssh = (tau_0 / (rho * g * layerThickness)) * (ds.fCell / beta) *\
          (1. - ds.xCell / L_x) * pi * np.sin(pi * ds.yCell / L_y) *\
          (1. - np.exp(-1. * ds.xCell / (2. * delta_m)) *
           (np.cos(gamma) + (1. / sqrt3) * np.sin(gamma)))

    return ssh
