import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset
from scipy.interpolate import griddata

from polaris import Step


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

        mesh_name : str
            The name of the mesh
        """
        super().__init__(test_case=test_case, name=name, subdir=subdir)
        self.add_input_file(
            filename='initial_state.nc',
            target='../initial_state/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')
        self.mesh_name = mesh_name
        self.add_output_file('vorticity.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.figure(1, figsize=(12.0, 6.0))

        ncfileIC = Dataset('initial_state.nc', 'r')
        ncfile = Dataset('output.nc', 'r')
        var1 = ncfile.variables['normalizedRelativeVorticityEdge'][6, :, 0]
        var2 = ncfile.variables['normalizedPlanetaryVorticityEdge'][6, :, 0]
        var = var1 + var2
        latEdge = ncfileIC.variables['latEdge'][:]
        lonEdge = ncfileIC.variables['lonEdge'][:]
        latEdge = latEdge * 180 / np.pi
        lonEdge = lonEdge * 180 / np.pi - 180
        xi = np.linspace(-180, 180, 720)
        yi = np.linspace(0, 80, 180)
        X, Y = np.meshgrid(xi, yi)
        Z = griddata((lonEdge, latEdge), var, (X, Y), method='linear')
        Z = np.clip(Z, 0, 2.6e-8)
        plt.figure(figsize=(9.6, 4.8))
        plt.contourf(X, Y, Z, 200)
        plt.xlabel('longitude')
        plt.ylabel('latitude')
        plt.axis('scaled')
        plt.colorbar

        plt.savefig('vorticity.png')
