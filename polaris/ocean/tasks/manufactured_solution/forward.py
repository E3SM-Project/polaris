import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.convergence import ConvergenceForward
from polaris.ocean.tasks.manufactured_solution.exact_solution import (
    ExactSolution,
)


class Forward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of manufactured
    solution test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, component, name, resolution, subdir, init):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the test case in km

        subdir : str
            The subdirectory that the task belongs to

        init : polaris.Step
            The step which generates the mesh and initial condition
        """
        super().__init__(component=component,
                         name=name, subdir=subdir,
                         resolution=resolution, mesh=init, init=init,
                         package='polaris.ocean.tasks.manufactured_solution',
                         yaml_filename='forward.yaml',
                         graph_target=f'{init.path}/culled_graph.info',
                         output_filename='output.nc',
                         validate_vars=['layerThickness', 'normalVelocity'])

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        config = self.config
        model = config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')

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

        exact_solution = ExactSolution(self.config)
        options = {'config_manufactured_solution_amplitude':
                   float(exact_solution.eta0),
                   'config_manufactured_solution_wavelength_x':
                   float(exact_solution.lambda_x),
                   'config_manufactured_solution_wavelength_y':
                   float(exact_solution.lambda_y)}
        self.add_model_config_options(options, config_model='mpas-ocean')
