from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the
    external gravity wave case
    """

    def __init__(self, component, name, subdir, resolution, mesh,
                 init, graph_path, yaml_filename):
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
        """
        package = 'polaris.ocean.tasks.external_gravity_wave'
        validate_vars = ['normalVelocity', 'layerThickness']

        super().__init__(component=component, name=name, subdir=subdir,
                         resolution=resolution, mesh=mesh,
                         init=init, package=package,
                         yaml_filename=yaml_filename,
                         graph_path=graph_path,
                         output_filename='output.nc',
                         validate_vars=validate_vars)
