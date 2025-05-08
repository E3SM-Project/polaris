from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.convergence.forward import ConvergenceForward


class Forward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of
    merry-go-round test cases.

    Attributes
    ----------
    refinement_factor : float
        The factor by which to scale space, time or both

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    resolution : float
        The resolution of the test case in km
    """

    def __init__(
        self,
        component,
        name,
        refinement_factor,
        subdir,
        init,
        refinement='both',
    ):
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

        validate_vars = ['normalVelocity', 'tracer1', 'tracer2', 'tracer3']
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            refinement_factor=refinement_factor,
            mesh=init,
            init=init,
            refinement=refinement,
            package='polaris.tasks.ocean.merry_go_round',
            yaml_filename='forward.yaml',
            graph_target=f'{init.path}/culled_graph.info',
            output_filename='output.nc',
            validate_vars=validate_vars,
        )

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['merry_go_round']

        # no file to read from, so we'll compute it based on config options
        resolution = get_resolution_for_task(
            self.config, self.refinement_factor, refinement=self.refinement
        )

        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)

        return nx * ny
