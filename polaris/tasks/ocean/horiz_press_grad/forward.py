from polaris.ocean.model import OceanModelStep
from polaris.resolution import resolution_to_string


class Forward(OceanModelStep):
    """
    This step performs a forward run for a single time step, writing out
    the normal-velocity tendency (which is just the pressure gradient
    acceleration) along with other diagnostics.
    """

    def __init__(self, component, horiz_res, init, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        horiz_res : float
            The horizontal resolution in km

        init : polaris.tasks.ocean.horiz_press_grad.init.Init
            The init step for this resolution

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

        self.add_horiz_mesh_input_file(
            work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(work_dir_target=f'{init.path}/init.nc')

        validate_vars = ['NormalVelocityTend']
        self.add_output_file('output.nc', validate_vars=validate_vars)

    def setup(self):
        """
        Fill in config options in the forward.yaml file based on config options
        """
        super().setup()

        self.add_yaml_file(
            'polaris.tasks.ocean.horiz_press_grad',
            'forward.yaml',
        )
