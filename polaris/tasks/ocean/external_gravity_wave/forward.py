import time as time

from polaris.ocean.convergence.spherical import SphericalConvergenceForward
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the external
    gravity wave test case

    Attributes
    ----------
    do_restart : bool
        Whether this is a restart run
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        mesh,
        init,
        refinement_factor,
        refinement,
        dt_type,
        do_restart=False,
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

        mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        refinement_factor : float
            The factor by which to scale space, time or both

        refinement : str
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time

        dt_type : str, optional
            Type of time-stepping to use. One of 'global' or 'local'

        do_restart : bool, optional
            Whether this is a restart run
        """
        package = 'polaris.tasks.ocean.external_gravity_wave'
        validate_vars = ['normalVelocity', 'layerThickness']

        if dt_type == 'local':
            graph_target = f'{init.path}/graph.info'
        else:
            graph_target = f'{mesh.path}/graph.info'

        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh=mesh,
            init=init,
            package=package,
            yaml_filename='forward.yaml',
            output_filename='output.nc',
            validate_vars=validate_vars,
            graph_target=graph_target,
            refinement_factor=refinement_factor,
            refinement=refinement,
        )
        self.do_restart = do_restart
        self.dt_type = dt_type

        if dt_type == 'local':
            self.add_yaml_file(
                'polaris.tasks.ocean.external_gravity_wave',
                'local_time_step.yaml',
            )



class ReferenceForward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of external
    gravity wave tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km

    dt_type : str, optional
        Type of time-stepping to use. One of 'global' or 'local'

    dt : float
        The model time step in seconds
    """

    def __init__(
        self,
        component,
        resolution,
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        mesh=None,
        init=None,
        dt_type='global',
        dt=None,
    ):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the task in km

        name : str
            the name of the task

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

        graph_target : str, optional
            The graph file name (relative to the base work directory).
            If none, it will be created.
        """
        package = 'polaris.tasks.ocean.external_gravity_wave'
        yaml_filename = 'forward.yaml'
        validate_vars = ['normalVelocity', 'layerThickness']

        if dt_type == 'local':
            graph_target = f'{init.path}/graph.info'
        else:
            graph_target = f'{mesh.path}/graph.info'

        self.resolution = resolution
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            graph_target=graph_target,
        )

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/initial_state.nc',
        )

        if dt_type == 'local':
            self.add_yaml_file(
                'polaris.tasks.ocean.external_gravity_wave',
                'local_time_step.yaml',
            )

        self.add_output_file(
            filename='output.nc',
            validate_vars=validate_vars,
        )

        self.dt = dt
        self.package = package
        self.yaml_filename = yaml_filename

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
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
        dt = self.dt

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        dt_str = get_time_interval_string(seconds=dt)

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
            run_duration=run_duration_str,
            output_interval=output_interval_str,
            output_freq=f'{output_freq}',
        )

        self.add_yaml_file(
            self.package,
            self.yaml_filename,
            template_replacements=replacements,
        )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')
