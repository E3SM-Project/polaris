from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of overflow
    test cases.

    Attributes
    ----------
    config_section : str
        The section in the config file for this test case, used to get
        the run duration and output interval

    horiz_adv_order : int or None
        The horizontal advection order for the test case

    nu : float or None
       The Laplacian viscosity to use for this forward step
    """

    def __init__(
        self,
        component,
        init,
        config_section,
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        horiz_adv_order=None,
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

        task_name : str
           The name of the task that this step belongs to

        init : polaris.ocean.tasks.internal_wave.init.Init
            the initial state step

        config_section : str
            The section in the config file for this test case, used to get
            the run duration and output interval

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

        horiz_adv_order : int, optional
            The horizontal advection order for the test case (if different
            from the default for the test group)

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
        self.config_section = config_section
        self.horiz_adv_order = horiz_adv_order
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
        resolution = config.getfloat('overflow', 'resolution')
        dt_per_km = config.getfloat('overflow', 'dt_per_km')
        btr_dt_per_km = config.getfloat('overflow', 'btr_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * resolution)
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * resolution
        )
        if self.nu is None:
            self.nu = config.getfloat('overflow', 'default_viscosity')

        if self.horiz_adv_order is None:
            self.horiz_adv_order = config.getint(
                'overflow', 'default_horiz_adv_order'
            )
        section = config[self.config_section]
        run_duration = section.getfloat('run_duration')
        run_duration_units = section.get('run_duration_units')
        output_interval = section.getfloat('output_interval')
        output_units = section.get('output_interval_units')
        output_freq = int(output_interval)
        run_duration_str = self._interval_to_string(
            run_duration, run_duration_units
        )
        output_interval_str = self._interval_to_string(
            output_interval, output_units
        )

        time_integrator = config.get('overflow', 'time_integrator')
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
            run_duration_units=run_duration_units,
            output_interval=output_interval_str,
            nu=self.nu,
            output_freq=f'{output_freq}',
            output_freq_units=output_units,
            horiz_adv_order=self.horiz_adv_order,
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.overflow',
            'forward.yaml',
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

    @staticmethod
    def _interval_to_string(interval, units):
        """
        Convert a time interval to a string in the format "DDDD_HH:MM:SS.SS"
        """
        if units == 'days':
            interval_str = get_time_interval_string(days=interval)
        elif units == 'hours':
            interval_str = get_time_interval_string(seconds=interval * 3600.0)
        elif units == 'minutes':
            interval_str = get_time_interval_string(seconds=interval * 60.0)
        elif units == 'seconds':
            interval_str = get_time_interval_string(seconds=interval)
        else:
            raise ValueError(f'Unexpected time interval units: {units}')
        return interval_str
