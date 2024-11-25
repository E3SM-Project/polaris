from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(self, component, name, subdir, mesh, init,
                 refinement_factor, refinement='both'):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        resolution : float
            The resolution of the (uniform) mesh in km

        mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        time_refinement_factor : float
            The amount by which to scale dt_per_km and btr_dt_per_km
        """
        package = 'polaris.ocean.tasks.cosine_bell'
        validate_vars = ['normalVelocity', 'tracer1']
        super().__init__(component=component, name=name, subdir=subdir,
                         mesh=mesh, init=init, package=package,
                         yaml_filename='forward.yaml',
                         output_filename='output.nc',
                         validate_vars=validate_vars,
                         graph_target=f'{mesh.path}/graph.info',
                         refinement_factor=refinement_factor,
                         refinement=refinement)
