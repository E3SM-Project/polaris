from polaris.ocean.model import OceanModelStep, get_time_interval_string


class SphericalConvergenceForward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of a spherical
    convergence test

    Attributes
    ----------
    resolution : float
        The resolution of the (uniform) mesh in km

    package : Package
        The package name or module object that contains the YAML file

    yaml_filename : str
        A YAML file that is a Jinja2 template with model config options

    """

    def __init__(self, component, name, subdir, resolution, base_mesh, init,
                 package, yaml_filename='forward.yaml', options=None,
                 output_filename='output.nc', validate_vars=None):
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

        package : Package
            The package name or module object that contains the YAML file

        yaml_filename : str, optional
            A YAML file that is a Jinja2 template with model config options

        options : dict, optional
            A dictionary of options and value to replace model config options
            with new values

        output_filename : str, optional
            The output file that will be written out at the end of the forward
            run

        validate_vars : list of str, optional
            A list of variables to validate against a baseline if requested
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         openmp_threads=1)

        self.resolution = resolution
        self.package = package
        self.yaml_filename = yaml_filename

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        if options is not None:
            self.add_model_config_options(options=options)

        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/initial_state.nc')
        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{base_mesh.path}/graph.info')

        self.add_output_file(filename=output_filename,
                             validate_vars=validate_vars)

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # use a heuristic based on QU30 (65275 cells) and QU240 (10383 cells)
        cell_count = 6e8 / self.resolution**2
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Set the model time step from config options at setup and runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        section = config['convergence_forward']

        time_integrator = section.get('time_integrator')

        # dt is proportional to resolution: default 30 seconds per km
        if time_integrator == 'RK4':
            dt_per_km = section.getfloat('rk4_dt_per_km')
        else:
            dt_per_km = section.getfloat('split_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * self.resolution)

        # btr_dt is also proportional to resolution: default 1.5 seconds per km
        btr_dt_per_km = section.getfloat('btr_dt_per_km')
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * self.resolution)

        run_duration = section.getfloat('run_duration')
        run_duration_str = get_time_interval_string(days=run_duration)

        output_interval = section.getfloat('output_interval')
        output_interval_str = get_time_interval_string(days=output_interval)

        replacements = dict(
            time_integrator=time_integrator,
            dt=dt_str,
            btr_dt=btr_dt_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
        )

        self.add_yaml_file(self.package, self.yaml_filename,
                           template_replacements=replacements)
