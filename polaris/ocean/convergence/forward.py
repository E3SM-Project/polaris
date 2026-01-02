from polaris.ocean.convergence import get_timestep_for_task
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class ConvergenceForward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of a spherical
    convergence test

    Attributes
    ----------
    package : Package
        The package name or module object that contains the YAML file

    yaml_filename : str
        A YAML file that is a Jinja2 template with model config options

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    refinement_factor : float
        Refinement factor use to scale space, time or both depending on
        refinement option
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        refinement_factor,
        mesh,
        init,
        package,
        yaml_filename='forward.yaml',
        mesh_input_filename='mesh.nc',
        options=None,
        graph_target=None,
        output_filename='output.nc',
        validate_vars=None,
        check_properties=None,
        refinement='both',
    ):
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

        refinement_factor : float
            Refinement factor use to scale space, time or both depending on
            refinement option

        package : Package
            The package name or module object that contains the YAML file

        yaml_filename : str, optional
            A YAML file that is a Jinja2 template with model config options

        mesh_input_filename : str, optional
            The filename of the mesh produced by the ``mesh`` step.  This file
            will be symlinked into the work directory as ``mesh.nc`` for the
            ocean model to use.

        options : dict, optional
            A nested dictionary of options and value for each ``config_model``
            to replace model config options with new values

        graph_target : str, optional
            The graph file name (relative to the base work directory).
            If none, it will be created.

        output_filename : str, optional
            The output file that will be written out at the end of the forward
            run

        validate_vars : list of str, optional
            A list of variables to validate against a baseline if requested

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            openmp_threads=1,
            graph_target=graph_target,
        )

        self.refinement = refinement
        self.refinement_factor = refinement_factor
        self.package = package
        self.yaml_filename = yaml_filename

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        if options is not None:
            for config_model in options:
                self.add_model_config_options(
                    options=options[config_model], config_model=config_model
                )

        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/initial_state.nc'
        )
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{mesh.path}/{mesh_input_filename}',
        )

        self.add_output_file(
            filename=output_filename,
            validate_vars=validate_vars,
            check_properties=check_properties,
        )

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        raise ValueError(
            'compute_cell_count method must be overridden by '
            'spherical or planar method'
        )

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
        refinement_factor = self.refinement_factor

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        timestep, btr_timestep = get_timestep_for_task(
            config, refinement_factor, refinement=self.refinement
        )
        dt_str = get_time_interval_string(seconds=timestep)
        btr_dt_str = get_time_interval_string(seconds=btr_timestep)

        s_per_hour = 3600.0
        section = config['convergence_forward']
        run_duration = section.getfloat('run_duration')
        run_duration_str = get_time_interval_string(
            seconds=run_duration * s_per_hour
        )

        output_interval = section.getfloat('output_interval')
        output_interval_str = get_time_interval_string(
            seconds=output_interval * s_per_hour
        )

        # For Omega, we want the output interval as a number of seconds
        output_freq = int(output_interval * s_per_hour)

        time_integrator = section.get('time_integrator')
        time_integrator_map = dict([('RK4', 'RungeKutta4')])
        model = config.get('ocean', 'model')
        if model == 'omega':
            if time_integrator in time_integrator_map.keys():
                time_integrator = time_integrator_map[time_integrator]
            else:
                print(
                    'Warning: mapping from time integrator '
                    f'{time_integrator} to omega not found, '
                    'retaining name given in config'
                )

        replacements = dict(
            time_integrator=time_integrator,
            dt=dt_str,
            btr_dt=btr_dt_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
            output_freq=f'{output_freq}',
        )

        self.add_yaml_file(
            self.package,
            self.yaml_filename,
            template_replacements=replacements,
        )
