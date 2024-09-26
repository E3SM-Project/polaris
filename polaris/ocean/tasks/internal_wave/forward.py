import time

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of internal wave
    test cases.

    Attributes
    ----------
    run_time_steps : int or None
        Number of time steps to run for
    """
    def __init__(self, component, init, name='forward', subdir=None,
                 indir=None, ntasks=None, min_tasks=None, openmp_threads=1,
                 nu=None, run_time_steps=None, vadv_method='standard'):
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

        nu : float, optional
            the viscosity (if different from the default for the test group)

        run_time_steps : int, optional
            Number of time steps to run for

        vadv_method : str, optional
            The vertical advection method, 'standard' or 'vlr'
        """
        self.run_time_steps = run_time_steps
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads,
                         graph_target=f'{init.path}/culled_graph.info')

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='initial_state.nc',
                            target=f'{init.path}/initial_state.nc')

        self.add_yaml_file('polaris.ocean.tasks.internal_wave',
                           'forward.yaml')

        if nu is not None:
            # update the viscosity to the requested value *after* loading
            # forward.yaml
            self.add_model_config_options(options=dict(config_mom_del2=nu),
                                          config_model='mpas-ocean')

        vadv_dict = {'standard': 'flux-form',
                     'vlr': 'remap'}
        self.add_model_config_options({
            'config_vert_advection_method': f"{vadv_dict[vadv_method]}"},
            config_model='mpas-ocean')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['layerThickness', 'normalVelocity'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['internal_wave']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
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

        options = dict()

        # dt is proportional to resolution: default 30 seconds per km
        resolution = config.getfloat('internal_wave', 'resolution')
        dt_per_km = config.getfloat('internal_wave', 'dt_per_km')
        dt = dt_per_km * resolution
        # https://stackoverflow.com/a/1384565/7728169
        options['config_dt'] = \
            time.strftime('%H:%M:%S', time.gmtime(dt))

        if self.run_time_steps is not None:
            # default run duration is a few time steps
            run_seconds = self.run_time_steps * dt
            options['config_run_duration'] = \
                time.strftime('%H:%M:%S', time.gmtime(run_seconds))
            options['config_stop_time'] = 'none'
        self.add_model_config_options(options=options,
                                      config_model='mpas-ocean')
