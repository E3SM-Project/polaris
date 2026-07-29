from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of seamount
    test cases.

    Attributes
    ----------
    task_name : str
       The name of the task that this step belongs to

    yaml_filename : str
       The name of the yaml file for this forward step

    nu : float
       The Laplacian viscosity to use for this forward step
    """

    def __init__(
        self,
        component,
        init,
        yaml_filename='forward.yaml',
        name='forward',
        task_name='default',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        nu=1000.0,
    ):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        task_name : str
           The name of the task that this step belongs to

        yaml_filename : str
           The name of the yaml file for this forward step

        init : polaris.ocean.tasks.internal_wave.init.Init
            the initial state step

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use

        nu : float, optional
            the viscosity (if different from the default for the test group)
        """
        if min_tasks is None:
            min_tasks = ntasks
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            update_eos=True,
            graph_target=f'{init.path}/culled_graph.info',
        )
        self.task_name = task_name
        self.yaml_filename = yaml_filename
        self.nu = nu

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_horiz_mesh_input_file(
            work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(work_dir_target=f'{init.path}/init.nc')

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'layerThickness',
                'normalVelocity',
                'temperature',
            ],
        )

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        section = config['seamount']
        model = config.get('ocean', 'model')
        resolution = section.getfloat('resolution')

        # MPAS-Ocean resolves the barotropic mode with a sub-step, so it can
        # take a much longer baroclinic step than Omega, which has no
        # split-explicit integrator
        if model == 'omega':
            dt_per_km = section.getfloat('omega_dt_per_km')
            time_integrator = _omega_time_integrator(
                section.get('omega_time_integrator')
            )
        else:
            dt_per_km = section.getfloat('dt_per_km')
            time_integrator = section.get('time_integrator')

        btr_dt_per_km = section.getfloat('btr_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * resolution)
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * resolution
        )

        task_section = config[f'seamount_{self.task_name}']
        run_duration = task_section.getfloat('run_duration')
        output_interval = task_section.getfloat('output_interval')
        run_duration_str = get_time_interval_string(
            seconds=run_duration * 86400.0
        )
        output_interval_str = get_time_interval_string(
            seconds=output_interval * 3600.0
        )

        replacements = dict(
            dt=dt_str,
            btr_dt=btr_dt_str,
            time_integrator=time_integrator,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
            # Omega's History stream takes an integer frequency, so express
            # the interval in seconds to avoid truncating a fractional hour
            output_freq=f'{round(output_interval * 3600.0)}',
            output_freq_units='seconds',
            horiz_adv_order=section.getint('horiz_adv_order'),
            bottom_drag_coeff=section.getfloat('bottom_drag_coeff'),
            nu=self.nu,
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.seamount',
            self.yaml_filename,
            template_replacements=replacements,
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
        section = self.config['seamount']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        cell_count = nx * ny
        return cell_count


def _omega_time_integrator(time_integrator):
    """
    Map an MPAS-Ocean time-integrator name to its Omega equivalent, leaving
    names that are already Omega's alone.
    """
    time_integrator_map = dict([('RK4', 'RungeKutta4')])
    if time_integrator in time_integrator_map:
        return time_integrator_map[time_integrator]
    return time_integrator
