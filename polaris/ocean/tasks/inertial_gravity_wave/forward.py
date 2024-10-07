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
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, component, name, refinement_factor, subdir,
                 init, refinement='both'):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the test case in km

        subdir : str
            The subdirectory that the step belongs to

        init : polaris.Step
            The step which generates the mesh and initial condition
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
