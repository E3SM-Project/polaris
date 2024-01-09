from mpas_tools.cime.constants import constants

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of baroclinic
    channel tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """
    def __init__(self, component, resolution, mesh, init,
                 name='forward', subdir=None, indir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1,
                 do_restart=False, tidal_forcing=False):
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
        """
        if do_restart:
            name = 'restart'
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.resolution = resolution
        self.do_restart = do_restart
        self.tidal_forcing = tidal_forcing

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='init.nc',
                            work_dir_target=f'{init.path}/output.nc')
        self.add_input_file(filename='graph.info',
                            work_dir_target=f'{mesh.path}/culled_graph.info')
        if do_restart:
            self.add_input_file(filename='restarts',
                                target='../forward/restarts')
        self.add_output_file(
            filename='output.nc',
            validate_vars=['temperature', 'salinity', 'layerThickness',
                           'normalVelocity'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['ice_shelf_2d']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count

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

        config = self.config
        if self.tidal_forcing:
            section = config['ice_shelf_2d_default_tidal_forcing']
            run_duration = section.getfloat('forward_run_duration')
            run_duration = run_duration * constants['SHR_CONST_CDAY']
        else:
            section = config['ice_shelf_2d_default']
            run_duration = section.getfloat('forward_run_duration')
            run_duration = run_duration * 60.
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

        do_restart_str = 'false'
        if self.do_restart:
            do_restart_str = 'true'

        # There must be only one output time slice in forward because the
        # restart run comparison assumes this
        if self.do_restart:
            output_interval = run_duration / 2.
        else:
            output_interval = run_duration
        output_interval_str = get_time_interval_string(
            seconds=output_interval)
        run_duration_str = output_interval_str

        start_time = '0001-01-01_00:00:00'
        if self.do_restart:
            start_time = f"{start_time.split('_')[0]}_" \
                         f"{run_duration_str.split('_')[1]}"

        if self.tidal_forcing:
            land_ice_flux_mode = 'pressure_only'
        else:
            land_ice_flux_mode = 'standalone'

        replacements = dict(
            do_restart=do_restart_str,
            start_time=start_time,
            time_integrator=time_integrator,
            dt=dt_str,
            btr_dt=btr_dt_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
            land_ice_flux_mode=land_ice_flux_mode,
        )
        self.add_yaml_file('polaris.ocean.tasks.ice_shelf_2d',
                           'forward.yaml',
                           template_replacements=replacements)
        if self.tidal_forcing:
            self.add_yaml_file('polaris.ocean.tasks.ice_shelf_2d',
                               'tidal_forcing.yaml')
        else:
            self.add_yaml_file('polaris.ocean.tasks.ice_shelf_2d',
                               'global_stats.yaml',
                               template_replacements=replacements)

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')
