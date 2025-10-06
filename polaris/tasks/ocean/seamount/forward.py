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

        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/init.nc',
        )

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
        resolution = config.getfloat('seamount', 'resolution')
        dt_per_km = config.getfloat('seamount', 'dt_per_km')
        btr_dt_per_km = config.getfloat('seamount', 'btr_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * resolution)
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * resolution
        )
        section = config[f'seamount_{self.task_name}']
        run_duration = section.getfloat('run_duration')
        output_interval = section.getfloat('output_interval')
        if self.task_name == 'rpe':
            run_duration_str = get_time_interval_string(days=run_duration)
            output_interval_str = get_time_interval_string(
                days=output_interval
            )
        else:
            run_duration_str = get_time_interval_string(
                seconds=run_duration * 60.0
            )
            output_interval_str = get_time_interval_string(
                seconds=output_interval
            )

        replacements = dict(
            dt=dt_str,
            btr_dt=btr_dt_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
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
