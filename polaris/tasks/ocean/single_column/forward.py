from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of single_column
    test cases.

    Attributes
    ----------
    resources_fixed : bool
        Whether resources were set already and shouldn't be updated
        algorithmically
    """

    def __init__(
        self,
        component,
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        validate_vars=None,
        task_name='',
        enable_vadv=True,
    ):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the step

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use

        validate_vars : list, optional
            A list of variable names to compare with a baseline (if one is
            provided)

        task_name : str, optional
            the name of the test case
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
        )

        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(
            filename='initial_state.nc', target='../init/initial_state.nc'
        )
        self.add_input_file(filename='forcing.nc', target='../init/forcing.nc')
        self.add_input_file(
            filename='graph.info', target='../init/culled_graph.info'
        )

        self.add_yaml_file('polaris.tasks.ocean.single_column', 'forward.yaml')
        self.add_yaml_file(
            f'polaris.tasks.ocean.single_column.{task_name}', 'forward.yaml'
        )

        self.add_output_file(filename='output.nc', validate_vars=validate_vars)

        self.resources_fixed = ntasks is not None

        self.task_name = task_name

        self.enable_vadv = enable_vadv

    def dynamic_model_config(self, at_setup):
        if self.task_name == 'ekman':
            nu = self.config.getfloat(
                'single_column_ekman', 'vertical_viscosity'
            )
            self.add_model_config_options(
                options={'config_cvmix_background_viscosity': nu},
                config_model='mpas-ocean',
            )
        if not self.enable_vadv:
            self.add_model_config_options(
                options={
                    'config_vert_coord_movement': 'impermeable_interfaces',
                    'config_disable_vel_vadv': True,
                    'config_disable_tr_adv': True,
                },
                config_model='mpas-ocean',
            )
