import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.tests.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)


class Analysis(Step):
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
        super().__init__(test_case=test_case, name='analysis')
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
        config = self.config
        resolutions = self.resolutions

        section = config['inertial_gravity_wave']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        f0 = section.getfloat('f0')
        eta0 = section.getfloat('eta0')
        npx = section.getfloat('nx')
        npy = section.getfloat('ny')

        rmse = []
        for res in resolutions:
            init = xr.open_dataset(f'init_{res}km.nc')
            ds = xr.open_dataset(f'output_{res}km.nc')
            exact = ExactSolution(init, eta0, npx, npy, lx, ly)
