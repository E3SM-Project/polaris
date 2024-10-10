from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(self, component, name, subdir, resolution, mesh, init):
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
        package = 'polaris.ocean.tasks.geostrophic'
        validate_vars = ['temperature',
                         'salinity',
                         'layerThickness',
                         'normalVelocity']
        super().__init__(component=component, name=name, subdir=subdir,
                         resolution=resolution, mesh=mesh,
                         init=init, package=package,
                         yaml_filename='forward.yaml',
                         output_filename='output.nc',
                         validate_vars=validate_vars,
                         graph_target=f'{mesh.path}/graph.info')
