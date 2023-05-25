import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.jet import init as jet_init
from netCDF4 import Dataset
from scipy.interpolate import griddata

from polaris import Step
from polaris.ocean.vertical import init_vertical_coord


class Viz(Step):
    """
    A step for plotting fields from the galewsky jet output

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, test_case, name, subdir, mesh_name):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory in the test case's work directory for the step

        viz_map : polaris.ocean.tests.galewsky_jet.test_balance.viz.VizMap
            The step for creating a mapping files, also used to remap data
            from the MPAS mesh to a lon-lat grid

        mesh_name : str
            The name of the mesh
        """
        super().__init__(test_case=test_case, name=name, subdir=subdir)
        self.add_input_file(
            filename='mesh.nc',
            target='../base_mesh/mesh.nc')
        self.add_input_file(
            filename='initial_state.nc',
            target='../initial_state/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')
        self.mesh_name = mesh_name
        self.add_output_file('init_unperturbed.nc')
        self.add_output_file('height.png')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        ds = xr.open_dataset('mesh.nc')
        x_cell = ds.xCell
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)
        init_vertical_coord(config, ds)
        jet_init(name='mesh.nc', save='velocity_ic.nc',
                 rsph=6371220.0, pert=False)
        ds2 = xr.open_dataset('velocity_ic.nc')
        unrm_array, _ = xr.broadcast(ds2.u, ds.refZMid)
        ds['normalVelocity'] = unrm_array
        h_array, _ = xr.broadcast(ds2.h, ds.refZMid)
        ds['layerThickness'] = h_array
        write_netcdf(ds, 'init_unperturbed.nc')

        ncfileIC = Dataset('initial_state.nc', 'r')
        ncfileIC2 = Dataset('init_unperturbed.nc', 'r')
        ncfile = Dataset('output.nc', 'r')
        var1 = ncfileIC2.variables['layerThickness'][0, :, 0]
        var2 = ncfile.variables['layerThickness'][36, :, 0]
        var = var2 - var1
        latCell = ncfileIC.variables['latCell'][:]
        lonCell = ncfileIC.variables['lonCell'][:]
        latCell = latCell * 180 / np.pi
        lonCell = lonCell * 180 / np.pi - 180
        xi = np.linspace(-180, 180, 720)
        yi = np.linspace(-80, 80, 180)
        X, Y = np.meshgrid(xi, yi)
        Z = griddata((lonCell, latCell), var, (X, Y), method='linear')
        # Z = np.clip(Z, 0, 2.6e-8)
        plt.figure(figsize=(9.6, 4.8))
        plt.contour(X, Y, Z, 20)
        plt.xlabel('longitude')
        plt.ylabel('latitude')
        plt.axis('scaled')
        plt.colorbar

        plt.savefig('height.png')
