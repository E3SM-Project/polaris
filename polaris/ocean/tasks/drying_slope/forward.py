import time

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of drying
    slope tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km

    dt : float
        The model time step in seconds

    btr_dt : float
        The model barotropic time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
    """
    def __init__(self, component, resolution, name='forward', subdir=None,
                 indir=None, ntasks=None, min_tasks=None, openmp_threads=1,
                 time_integrator='rk4', damping_coeff=None,
                 coord_type='sigma', forcing_type='tidal_cycle',
                 drag_type='constant_and_rayleigh', baroclinic=False,
                 method='ramp', run_time_steps=None):
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

        run_time_steps : int or None
            Number of time steps to run for
        """
        if drag_type == 'constant_and_rayleigh':
            if coord_type == 'single_layer':
                raise ValueError(f'Drag type {drag_type} is not supported '
                                 f'with coordinate type {coord_type}')
            if damping_coeff is None:
                raise ValueError('Damping coefficient must be specified with '
                                 f'drag type {drag_type}')

        self.baroclinic = baroclinic
        self.resolution = resolution
        self.run_time_steps = run_time_steps
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.add_input_file(filename='initial_state.nc',
                            target='../init/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../init/culled_graph.info')
        self.add_input_file(filename='forcing.nc',
                            target='../init/forcing.nc')

        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_yaml_file('polaris.ocean.tasks.drying_slope',
                           'forward.yaml')

        options = dict()
        if coord_type == 'single_layer':
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')
            options['config_disable_thick_sflux'] = True
            options['config_disable_vel_hmix'] = True

        if method == 'ramp':
            options['config_zero_drying_velocity_ramp'] = True

        options['config_implicit_bottom_drag_type'] = drag_type
        # for drag types not specified here, defaults are used or given in
        # forward.yaml
        if drag_type == 'constant':
            options['config_implicit_constant_bottom_drag_coeff'] = \
                3.0e-3   # type: ignore[assignment]
        elif drag_type == 'constant_and_rayleigh':
            # update the damping coefficient to the requested value *after*
            # loading forward.yaml
            options['config_Rayleigh_damping_coeff'] = damping_coeff

        if baroclinic:
            self.add_yaml_file('polaris.ocean.tasks.drying_slope',
                               'baroclinic.yaml')

        forcing_dict = {'tidal_cycle': 'monochromatic',
                        'linear_drying': 'linear'}

        options['config_tidal_forcing_model'] = \
            forcing_dict[forcing_type]   # type: ignore[assignment]
        self.add_model_config_options(options=options)

        self.add_output_file(
            filename='output.nc',
            validate_vars=['temperature', 'salinity', 'layerThickness',
                           'normalVelocity'])

        self.dt = None
        self.btr_dt = None

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        if self.baroclinic:
            section = self.config['drying_slope_baroclinic']
        else:
            section = self.config['drying_slope_barotropic']
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

        options = dict()

        # dt is proportional to resolution: default 30 seconds per km
        section = config['drying_slope']
        time_integrator = section.get('time_integrator')
        options['config_time_integrator'] = time_integrator

        if time_integrator == 'RK4':
            dt_per_km = section.getfloat('rk4_dt_per_km')
        if time_integrator == 'split_explicit':
            dt_per_km = section.getfloat('split_dt_per_km')
            # btr_dt is also proportional to resolution
            btr_dt_per_km = config.getfloat('drying_slope', 'btr_dt_per_km')
            btr_dt = btr_dt_per_km * self.resolution
            options['config_btr_dt'] = \
                time.strftime('%H:%M:%S', time.gmtime(btr_dt))
            self.btr_dt = btr_dt
        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        options['config_dt'] = \
            time.strftime('%H:%M:%S', time.gmtime(dt))
        self.dt = dt

        if self.run_time_steps is not None:
            options['run_duration'] = time.strftime(
                '%H:%M:%S', time.gmtime(dt * self.run_time_steps))

        if self.baroclinic:
            section = self.config['drying_slope_baroclinic']
        else:
            section = self.config['drying_slope_barotropic']
        thin_film_thickness = section.getfloat('thin_film_thickness')
        options['config_drying_min_cell_height'] = thin_film_thickness
        options['config_zero_drying_velocity_ramp_hmin'] = \
            thin_film_thickness
        options['config_zero_drying_velocity_ramp_hmax'] = \
            thin_film_thickness * 10.

        self.add_model_config_options(options=options)
