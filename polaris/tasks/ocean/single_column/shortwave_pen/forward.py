from polaris.tasks.ocean.single_column.forward import Forward


class ShortwavePenForward(Forward):
    """
    A forward step for the ``shortwave_pen`` task that either applies the
    incident shortwave flux entirely in the surface layer (Omega's default
    behavior) or distributes it through the water column using Omega's
    penetrating-shortwave-radiation tendency term.

    Attributes
    ----------
    use_penetrating_sw : bool
        Whether to enable Omega's penetrating-shortwave-radiation tendency
        term and read the extinction-coefficient forcing file
    """

    def __init__(
        self,
        component,
        init,
        extinction,
        name,
        indir,
        use_penetrating_sw,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        validate_vars=None,
        run_duration_steps=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        init : polaris.Step
            The initial-condition step

        extinction : polaris.Step
            The step that creates the extinction-coefficient forcing file

        name : str
            The name of the step

        indir : str
            The directory the step is in

        use_penetrating_sw : bool
            Whether to enable the penetrating-shortwave-radiation tendency
            term

        ntasks : int, optional
            The number of tasks the step would ideally use

        min_tasks : int, optional
            The number of tasks the step requires

        openmp_threads : int, optional
            The number of OpenMP threads the step will use

        validate_vars : list, optional
            A list of variable names to compare with a baseline

        run_duration_steps : int, optional
            The number of time steps to run for, overriding the
            ``run_duration`` config option
        """
        super().__init__(
            component=component,
            init=init,
            name=name,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            validate_vars=validate_vars,
            task_name='shortwave_pen',
            run_duration_steps=run_duration_steps,
        )
        self.use_penetrating_sw = use_penetrating_sw
        if use_penetrating_sw:
            self.add_input_file(
                filename='shortwave_extinction_coeffs.nc',
                work_dir_target=(
                    f'{extinction.path}/shortwave_extinction_coeffs.nc'
                ),
            )

    def dynamic_model_config(self, at_setup):
        """
        Set the Omega config option that enables or disables the
        penetrating-shortwave-radiation tendency term
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        model = config.get('ocean', 'model')
        if model != 'omega':
            raise ValueError(
                'The shortwave_pen task requires Omega; MPAS-Ocean does not '
                'implement a penetrating-shortwave-radiation scheme.'
            )

        self.add_model_config_options(
            options={
                'PenetratingShortwaveTendencyEnable': (
                    self.use_penetrating_sw
                ),
            },
            config_model='Omega',
        )
        # radiative forcing only: isolate the effect of the shortwave
        # absorption profile from convective/shear-driven mixing
        self.add_model_config_options(
            options={
                'config_use_cvmix_convection': False,
                'config_use_cvmix_shear': False,
            },
            config_model='ocean',
        )
