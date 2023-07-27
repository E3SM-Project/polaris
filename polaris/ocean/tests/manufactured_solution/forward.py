import time

import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep
from polaris.ocean.tests.manufactured_solution.exact_solution import (
    ExactSolution,
)


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of manufactured
    solution test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, test_case, resolution,
                 ntasks=None, min_tasks=None, openmp_threads=1):
        """
        Create a new test case

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        resolution : km
            The resolution of the test case in km

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use
        """
        self.resolution = resolution
        super().__init__(test_case=test_case,
                         name=f'forward_{resolution}km',
                         subdir=f'{resolution}km/forward',
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.add_input_file(filename='initial_state.nc',
                            target='../init/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../init/culled_graph.info')

        self.add_output_file(filename='output.nc')

        self.add_yaml_file('polaris.ocean.config',
                           'single_layer.yaml')
        self.add_yaml_file('polaris.ocean.tests.manufactured_solution',
                           'forward.yaml')

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # no file to read from, so we'll compute it based on config options
        section = self.config['manufactured_solution']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Set the model time step from config options at setup and runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup=at_setup)

        # dt is proportional to resolution
        config = self.config
        section = config['manufactured_solution']
        dt_per_km = section.getfloat('dt_per_km')
        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        dt_str = time.strftime('%H:%M:%S', time.gmtime(dt))
        exact_solution = ExactSolution(config)
        options = {'config_dt': dt_str,
                   'config_manufactured_solution_amplitude':
                   exact_solution.eta0,
                   'config_manufactured_solution_wavelength_x':
                   exact_solution.lambda_x,
                   'config_manufactured_solution_wavelength_y':
                   exact_solution.lambda_y}
        self.add_model_config_options(options)
