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
        disable_coriolis=None,
        enable_restoring=False,
        constant_diff=False,
        conservation_intervals=None,
        check_properties=None,
        run_duration_steps=None,
        match_technique=None,
        use_langmuir_circulation=None,
        mpas_langmuir_mixing_opt=None,
        mpas_use_theory_wave=None,
        minimum_obl_under_sea_ice=None,
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

        check_properties : list of str, optional
            Conservation properties to check. If not provided, mass, salt and
            energy conservation are checked.

        match_technique : str, optional
            Omega KPP ``MatchTechnique`` override (``'SimpleShapes'`` or
            ``'MatchBoth'``). If not provided, the model default is used.
            The equivalent MPAS-Ocean ``config_cvmix_kpp_matching`` option is
            set to the same value.

        use_langmuir_circulation : bool, optional
            Omega KPP ``UseLangmuirTurbulence`` override.  If not provided,
            the model default is used.

        disable_coriolis : bool, optional
            Whether to disable Omega's ``PVTendencyEnable`` (which carries
            both relative and planetary vorticity/Coriolis in a single
            term), independent of ``enable_hadv``.  If not provided,
            defaults to ``not enable_hadv`` to preserve prior behavior.
            MPAS-Ocean has no equivalent option, so Coriolis there is
            always governed solely by the ``[coriolis]`` config section.
        """
        if disable_coriolis is None:
            disable_coriolis = not enable_hadv
        if not enable_vadv:
            name = f'{name}_no_vadv'
        if not enable_hadv:
            name = f'{name}_no_hadv'
        if enable_restoring:
            name = f'{name}_restoring'
        if constant_diff:
            name = f'{name}_constant'
        if match_technique is not None:
            name = f'{name}_{match_technique.lower()}'
        if use_langmuir_circulation is not None:
            suffix = 'langmuir' if use_langmuir_circulation else 'no_langmuir'
            name = f'{name}_{suffix}'
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            graph_target=f'{init.path}/culled_graph.info',
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
        if check_properties is None:
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

        self.run_duration_steps = run_duration_steps
        self.resources_fixed = ntasks is not None

        self.task_name = task_name

        self.enable_hadv = enable_hadv
        self.disable_coriolis = disable_coriolis
        self.enable_vadv = enable_vadv
        self.enable_restoring = enable_restoring

        self.constant_diff = constant_diff

        self.match_technique = match_technique
        self.use_langmuir_circulation = use_langmuir_circulation
        self.mpas_langmuir_mixing_opt = mpas_langmuir_mixing_opt
        self.mpas_use_theory_wave = mpas_use_theory_wave
        self.minimum_obl_under_sea_ice = minimum_obl_under_sea_ice

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        section = config['single_column']
        time_step = section.getfloat('time_step')
        if self.run_duration_steps is not None:
            if self.run_duration_steps > 0:
                # run for a given number of time steps, with output every step
                duration_seconds = self.run_duration_steps * time_step
                output_interval_seconds = time_step
            else:
                raise ValueError(
                    'run_duration_steps must be >0 but was '
                    f'{self.run_duration_steps}'
                )
        else:
            duration_seconds = section.getfloat('run_duration') * 86400.0
            output_interval_seconds = section.getfloat('output_interval')
        model = config.get('ocean', 'model')
        duration_str = get_time_interval_string(seconds=duration_seconds)
        dt_str = get_time_interval_string(seconds=time_step)
        output_interval_str = get_time_interval_string(
            seconds=output_interval_seconds
        )

        time_integrator = section.get('time_integrator')
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
                    'KETendencyEnable': False,
                }
            )
        if self.disable_coriolis:
            # PVTendencyEnable carries both relative vorticity and Coriolis
            # in one term, so it's gated separately from enable_hadv: tasks
            # that need Coriolis (e.g. wind-driven regimes) must not disable
            # it just to turn off horizontal advection.
            omega_options.update({'PVTendencyEnable': False})
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

        if self.match_technique is not None:
            omega_options.update(
                {
                    'MatchTechnique': self.match_technique,
                }
            )
            mpas_options.update(
                {
                    'config_cvmix_kpp_matching': self.match_technique,
                }
            )
        if self.use_langmuir_circulation is not None:
            omega_options.update(
                {
                    'UseLangmuirTurbulence': self.use_langmuir_circulation,
                }
            )
        if self.mpas_langmuir_mixing_opt is not None:
            mpas_options.update(
                {
                    (
                        'config_cvmix_kpp_langmuir_mixing_opt'
                    ): self.mpas_langmuir_mixing_opt,
                    # entrainment_opt is what actually boosts Vt2 in the
                    # bulk-Richardson search (and thus the OBL depth);
                    # mixing_opt alone only reshapes the in-layer
                    # diffusivity/viscosity profile.
                    (
                        'config_cvmix_kpp_langmuir_entrainment_opt'
                    ): self.mpas_langmuir_mixing_opt,
                }
            )
        if self.mpas_use_theory_wave is not None:
            mpas_options.update(
                {
                    (
                        'config_cvmix_kpp_use_theory_wave'
                    ): self.mpas_use_theory_wave,
                }
            )
        if self.minimum_obl_under_sea_ice is not None:
            omega_options.update(
                {
                    'MinimumOSBLUnderSeaIce': self.minimum_obl_under_sea_ice,
                }
            )
            mpas_options.update(
                {
                    (
                        'configure_cvmix_kpp_minimum_OBL_under_sea_ice'
                    ): self.minimum_obl_under_sea_ice,
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
