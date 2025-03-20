from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the sphere
    transport test case
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        base_mesh,
        init,
        case_name,
        refinement_factor,
        refinement,
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

        base_mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        case_name: str
            The name of the test case

        refinement_factor : float
            The factor by which to scale space, time or both

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        package = 'polaris.ocean.tasks.sphere_transport'
        flow_id = {
            'rotation_2d': 1,
            'nondivergent_2d': 2,
            'divergent_2d': 3,
            'correlated_tracers_2d': 4,
        }
        namelist_options = {
            'mpas-ocean': {
                'config_transport_tests_flow_id': flow_id[case_name]
            }
        }
        validate_vars = ['normalVelocity', 'tracer1', 'tracer2', 'tracer3']
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh=base_mesh,
            init=init,
            package=package,
            yaml_filename='forward.yaml',
            output_filename='output.nc',
            validate_vars=validate_vars,
            options=namelist_options,
            graph_target=f'{base_mesh.path}/graph.info',
            refinement_factor=refinement_factor,
            refinement=refinement,
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
