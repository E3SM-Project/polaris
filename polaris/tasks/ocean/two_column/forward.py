from polaris.ocean.model import OceanModelStep
from polaris.resolution import resolution_to_string


class Forward(OceanModelStep):
    """
    This step performs a forward run for a single time step, writing out
    the normal-velocity tendency (which is just the pressure gradient
    acceleration) along with other diagnostics.
    """

    def __init__(self, component, horiz_res, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        horiz_res : float
            The horizontal resolution in km

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of
        """
        self.horiz_res = horiz_res
        name = f'forward_{resolution_to_string(horiz_res)}'
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
        )

        init_dir = f'init_{resolution_to_string(horiz_res)}'
        self.add_input_file(
            filename='initial_state.nc',
            target=f'../{init_dir}/initial_state.nc',
        )
        self.add_input_file(
            filename='mesh.nc',
            target=f'../{init_dir}/culled_mesh.nc',
        )

        # TODO: remove as soon as Omega no longer hard-codes this file
        self.add_input_file(filename='OmegaMesh.nc', target='initial_state.nc')

        validate_vars = ['NormalVelocityTend']
        self.add_output_file('output.nc', validate_vars=validate_vars)

    def setup(self):
        """
        Fill in config options in the forward.yaml file based on config options
        """
        super().setup()

        rho0 = self.config.get('vertical_grid', 'rho0')
        if rho0 is None:
            raise ValueError(
                'rho0 must be specified in the config file under vertical_grid'
            )

        self.add_yaml_file(
            'polaris.tasks.ocean.two_column',
            'forward.yaml',
            template_replacements={'rho0': rho0},
        )
