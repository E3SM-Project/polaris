import time

from polaris.ocean.tasks.baroclinic_channel.forward import Forward


class RestartStep(Forward):
    """
    A forward model step in the restart test case
    """
    def __init__(self, component, resolution, name, indir):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the test case in km

        name : str
            the name of the test case

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        self.resolution = resolution
        super().__init__(component=component, name=name, indir=indir, ntasks=4,
                         min_tasks=4, openmp_threads=1,
                         resolution=resolution)

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        dt = self.dt
        if dt is None:
            raise ValueError('dt was not set in the Forward class as expected')

        if self.name == 'full_run':
            # 2 time steps without a restart
            do_restart = False
            start_time = 0.
            run_duration = 2. * dt
            output_interval = 2. * dt
        elif self.name == 'restart_run':
            # 1 time step from the restart at 1 time step
            do_restart = True
            start_time = dt
            run_duration = dt
            output_interval = dt
        else:
            raise ValueError(f'Unexpected step name {self.name}')

        # to keep the time formatting from getting too complicated, we'll
        # assume 2 time steps is never more than a day
        start_time_str = time.strftime('0001-01-01_%H:%M:%S',
                                       time.gmtime(start_time))

        run_duration_str = time.strftime('0000-00-00_%H:%M:%S',
                                         time.gmtime(run_duration))

        output_interval_str = time.strftime('0000-00-00_%H:%M:%S',
                                            time.gmtime(output_interval))

        package = 'polaris.ocean.tasks.baroclinic_channel.restart'
        replacements = dict(
            do_restart=do_restart,
            start_time=start_time_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
        )

        self.add_yaml_file(package=package,
                           yaml='forward.yaml',
                           template_replacements=replacements)
