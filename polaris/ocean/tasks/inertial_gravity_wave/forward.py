import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.convergence.forward import ConvergenceForward


class Forward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of inertial
    gravity wave test cases.

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
                         refinement=refinement,
                         refinement_factor=refinement_factor,
                         mesh=init, init=init,
                         package='polaris.ocean.tasks.inertial_gravity_wave',
                         yaml_filename='forward.yaml',
                         graph_target=f'{init.path}/culled_graph.info',
                         output_filename='output.nc',
                         validate_vars=['layerThickness', 'normalVelocity'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['inertial_gravity_wave']
        resolution = get_resolution_for_task(
            self.config, self.refinement_factor, refinement=self.refinement)
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        cell_count = nx * ny
        return cell_count
