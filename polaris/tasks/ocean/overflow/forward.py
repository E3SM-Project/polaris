from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of overflow
    test cases.
    """

    def __init__(
        self,
        component,
        init,
        package,
        yaml_filename='forward.yaml',
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        nu=None,
    ):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

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
            graph_target=f'{init.path}/culled_graph.info',
        )
        self.package = package
        self.yaml_filename = yaml_filename

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/init.nc',
        )

        if nu is not None:
            # update the viscosity to the requested value *after* loading
            # forward.yaml
            self.add_model_config_options(
                options=dict(config_mom_del2=nu), config_model='mpas-ocean'
            )

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'layerThickness',
                'normalVelocity',
                'temperature',
                'salinity',
            ],
        )

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        resolution = config.getfloat('overflow', 'resolution')
        dt_per_km = config.getfloat('overflow', 'dt_per_km')
        btr_dt_per_km = config.getfloat('overflow', 'btr_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * resolution)
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * resolution
        )
        replacements = dict(
            dt=dt_str,
            btr_dt=btr_dt_str,
        )
        self.add_yaml_file('polaris.tasks.ocean.overflow', 'forward.yaml')
        self.add_yaml_file(
            self.package,
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
        section = self.config['overflow']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        cell_count = nx * ny
        return cell_count
