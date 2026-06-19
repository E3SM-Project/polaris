from polaris.ocean.model import OceanModelStep, get_time_interval_string


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
        update_eos=True,
        enable_vadv=True,
        enable_restoring=False,
        constant_diff=False,
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
        if not enable_vadv:
            name = f'{name}_no_vadv'
        if enable_restoring:
            name = f'{name}_restoring'
        if constant_diff:
            name = f'{name}_constant'
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

        self.add_horiz_mesh_input_file(target='../init/culled_mesh.nc')
        self.add_vert_coord_input_file(target='../init/vert_coord.nc')
        self.add_init_input_file(target='../init/init.nc')
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
        self.enable_restoring = enable_restoring

        self.constant_diff = constant_diff

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')
            # Uncomment these lines when coeffs.nc has been added to the
            # database
            # self.add_input_file(
            #    target='coeffs.nc',
            #    filename='coeffs.nc',
            #    database='single_column',
            # )

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        time_integrator = self.config.get('single_column', 'time_integrator')
        duration = self.config.getfloat('single_column', 'run_duration')
        time_integrator_map = dict([('RK4', 'RungeKutta4')])
        model = self.config.get('ocean', 'model')
        if model == 'omega':
            if time_integrator in time_integrator_map.keys():
                time_integrator = time_integrator_map[time_integrator]
                duration_str = get_time_interval_string(days=duration)
            else:
                print(
                    'Warning: mapping from time integrator '
                    f'{time_integrator} to omega not found, '
                    'retaining name given in config'
                )
        else:
            duration_str = str(duration * 86400)
        shared_options = {
            'config_time_integrator': time_integrator,
            'config_run_duration': duration_str,
        }
        mpas_options = {}
        omega_options = {}

        if self.task_name == 'ekman':
            nu = self.config.getfloat(
                'single_column_ekman', 'vertical_viscosity'
            )
            shared_options.update({'config_cvmix_background_viscosity': nu})
        if not self.enable_vadv:
            mpas_options.update(
                {
                    'config_vert_coord_movement': 'impermeable_interfaces',
                }
            )
            shared_options.update(
                {
                    'config_disable_thick_vadv': True,
                    'config_disable_vel_vadv': True,
                    'config_disable_tr_adv': True,
                }
            )
            omega_options.update(
                {
                    'TracerVertAdvTendencyEnable': False,
                }
            )
        if self.enable_restoring:
            shared_options.update(
                {
                    'config_use_activeTracers_surface_restoring': True,
                }
            )

        if self.constant_diff:
            shared_options.update(
                {
                    'config_use_cvmix_convection': False,
                    'config_use_cvmix_shear': False,
                }
            )
        else:
            shared_options.update(
                {
                    'config_use_cvmix_convection': True,
                    'config_use_cvmix_shear': True,
                }
            )

        self.add_model_config_options(
            options=shared_options,
            config_model='ocean',
        )
        self.add_model_config_options(
            options=mpas_options,
            config_model='mpas-ocean',
        )
        self.add_model_config_options(
            options=omega_options,
            config_model='omega',
        )
