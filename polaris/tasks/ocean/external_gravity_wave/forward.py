from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case

    Attributes
    ----------
    do_restart : bool
        Whether this is a restart run
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        mesh,
        init,
        refinement_factor,
        refinement,
        dt_type,
        do_restart=False,
    ):
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

        mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        refinement_factor : float
            The factor by which to scale space, time or both

        refinement : str
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time

        dt_type : str, optional
            Type of time-stepping to use. One of 'global' or 'local'

        do_restart : bool, optional
            Whether this is a restart run
        """
        package = 'polaris.tasks.ocean.external_gravity_wave'
        validate_vars = ['normalVelocity', 'layerThickness']

        if dt_type == 'local':
            graph_target = f'{init.path}/graph.info'
        else:
            graph_target = f'{mesh.path}/graph.info'

        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh=mesh,
            init=init,
            package=package,
            yaml_filename='forward.yaml',
            output_filename='output.nc',
            validate_vars=validate_vars,
            graph_target=graph_target,
            refinement_factor=refinement_factor,
            refinement=refinement,
        )
        self.do_restart = do_restart
        self.dt_type = dt_type

        if dt_type == 'local':
            self.add_yaml_file(
                'polaris.tasks.ocean.external_gravity_wave',
                'local_time_step.yaml',
            )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')
