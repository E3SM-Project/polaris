import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string
from polaris.ocean.resolution import resolution_to_subdir


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of inertial
    gravity wave test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, component, resolution, taskdir,
                 ntasks=None, min_tasks=None, openmp_threads=1):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the test case in km

        taskdir : str
            The subdirectory that the task belongs to

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use
        """
        self.resolution = resolution
        mesh_name = resolution_to_subdir(resolution)
        super().__init__(component=component,
                         name=f'forward_{mesh_name}',
                         subdir=f'{taskdir}/forward/{mesh_name}',
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.add_input_file(filename='initial_state.nc',
                            target=f'../../init/{mesh_name}/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target=f'../../init/{mesh_name}/culled_graph.info')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['layerThickness', 'normalVelocity'])

        self.package = 'polaris.ocean.tasks.inertial_gravity_wave'
        self.yaml_filename = 'forward.yaml'

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['inertial_gravity_wave']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
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

        # dt is proportional to resolution
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
