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
        init,
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        validate_vars=None,
        task_name='',
        task_package=None,
        update_eos=True,
        enable_vadv=True,
        enable_hadv=True,
        enable_restoring=False,
        constant_diff=False,
        conservation_intervals=None,
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

        task_package : str, optional
            the python package containing the task's ``forward.yaml``.  If not
            provided, it is assumed to be
            ``polaris.tasks.ocean.single_column.<task_name>``

        conservation_intervals : list of tuple, optional
            The time intervals over which to check conservation, each a tuple
            of the baseline (``'init'`` or a time index in ``output.nc``) and
            the time index in ``output.nc`` at the end of the interval.  By
            default, conservation is checked between the initial condition
            and the end of the run.
        """
        if not enable_vadv:
            name = f'{name}_no_vadv'
        if not enable_hadv:
            name = f'{name}_no_hadv'
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

        self.add_horiz_mesh_input_file(
            work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(work_dir_target=f'{init.path}/init.nc')
        self.add_input_file(
            filename='forcing.nc', work_dir_target=f'{init.path}/forcing.nc'
        )
        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{init.path}/culled_graph.info',
        )

        self.add_yaml_file('polaris.ocean.config', 'output.yaml')
        if task_package is None:
            task_package = f'polaris.tasks.ocean.single_column.{task_name}'
        self.task_package = task_package

        self.add_output_file(
            filename='output.nc',
            validate_vars=validate_vars,
        )
        if conservation_intervals is None:
            conservation_intervals = [('init', -1)]
        check_properties = [
            'mass conservation',
            'salt conservation',
            'energy conservation',
        ]
        for baseline, time_index_end in conservation_intervals:
            self.add_property_check(
                filename='output.nc',
                check_properties=check_properties,
                baseline=baseline,
                time_index_end=time_index_end,
            )

        self.resources_fixed = ntasks is not None

        self.task_name = task_name

        self.enable_hadv = enable_hadv
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
            self.add_input_file(
                target='coeffs.nc',
                filename='coeffs.nc',
                database='single_column',
            )

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        section = config['single_column']
        time_integrator = section.get('time_integrator')
        time_step = section.getfloat('time_step')
        run_duration_steps = section.getint('run_duration_steps')
        if run_duration_steps > 0:
            # run for a given number of time steps, with output every step
            duration_seconds = run_duration_steps * time_step
            output_interval_seconds = time_step
        else:
            duration_seconds = section.getfloat('run_duration') * 86400.0
            output_interval_seconds = section.getfloat('output_interval')
        model = config.get('ocean', 'model')
        if model == 'omega':
            duration_str = get_time_interval_string(seconds=duration_seconds)
        else:
            duration_str = str(duration_seconds)
        dt_str = get_time_interval_string(seconds=time_step)
        output_interval_str = get_time_interval_string(
            seconds=output_interval_seconds
        )
        time_integrator_map = dict([('RK4', 'RungeKutta4')])
        if model == 'omega':
            if time_integrator in time_integrator_map.keys():
                time_integrator = time_integrator_map[time_integrator]
            else:
                print(
                    'Warning: mapping from time integrator '
                    f'{time_integrator} to omega not found, '
                    'retaining name given in config'
                )
        else:
            duration_str = str(duration_seconds)

        # the task's yaml file may use these to set the output interval
        self.add_yaml_file(
            'polaris.tasks.ocean.single_column',
            'forward.yaml',
            template_replacements=dict(
                dt=dt_str,
                run_duration=duration_str,
                time_integrator=time_integrator,
            ),
        )
        self.add_yaml_file(
            self.task_package,
            'forward.yaml',
            template_replacements=dict(
                output_interval=output_interval_str,
                output_freq=f'{int(output_interval_seconds)}',
            ),
        )

        shared_options = {}
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
        if not self.enable_hadv:
            # This makes it inconsistent with MPAS-O, which cannot turn off
            # hadv without also turning off vadv
            omega_options.update(
                {
                    'TracerHorzAdvTendencyEnable': False,
                    'PVTendencyEnable': False,
                    'KETendencyEnable': False,
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
            config_model='Omega',
        )
