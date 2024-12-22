import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.convergence.forward import ConvergenceForward
from polaris.ocean.tasks.manufactured_solution.exact_solution import (
    ExactSolution,
)


class Forward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of manufactured
    solution test cases.

    Attributes
    ----------
    refinement_factor : float
        The factor by which to scale space, time or both

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time
    """
    def __init__(self, component, name, refinement_factor, subdir,
                 init, refinement='both'):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        refinement_factor : float
            The factor by which to scale space, time or both

        subdir : str
            The subdirectory that the task belongs to

        init : polaris.Step
            The step which generates the mesh and initial condition

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        super().__init__(component=component,
                         name=name, subdir=subdir,
                         refinement_factor=refinement_factor,
                         mesh=init, init=init, refinement=refinement,
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
        resolution = get_resolution_for_task(
            self.config, self.refinement_factor, refinement=self.refinement)
        section = self.config['manufactured_solution']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
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
