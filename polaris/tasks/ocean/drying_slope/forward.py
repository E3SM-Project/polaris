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

    baroclinic : logical
        Whether this test case is the baroclinic version

    dt : float
        The model time step in seconds

    btr_dt : float
        The model barotropic time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
    """

    def __init__(
        self,
        component,
        resolution,
        init,
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        damping_coeff=None,
        coord_type='sigma',
        forcing_type='tidal_cycle',
        drag_type='constant_and_rayleigh',
        baroclinic=False,
        method='ramp',
        run_time_steps=None,
        graph_target='graph.info',
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

        coord_type : str, optional
            The vertical coordinate type

        forcing_type : str, optional
            The forcing type to apply at the "tidal" boundary as a namelist
            option

        method : str, optional
            The type of wetting and drying algorithm to use

        drag_type : str, optional
            The bottom drag type to apply as a namelist option

        time_integrator : str, optional
            The time integration scheme to apply as a namelist option

        run_time_steps : int or None
            Number of time steps to run for
        """
        if drag_type == 'constant_and_rayleigh':
            if coord_type == 'single_layer':
                raise ValueError(
                    f'Drag type {drag_type} is not supported '
                    f'with coordinate type {coord_type}'
                )
            if damping_coeff is None:
                raise ValueError(
                    'Damping coefficient must be specified with '
                    f'drag type {drag_type}'
                )

        self.damping_coeff = damping_coeff
        self.drag_type = drag_type
        self.baroclinic = baroclinic
        self.coord_type = coord_type
        self.forcing_type = forcing_type
        self.method = method
        self.resolution = resolution
        self.run_time_steps = run_time_steps
        self.yaml_filename = 'forward.yaml'
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

        self.add_yaml_file('polaris.ocean.config', 'output.yaml')
        if self.coord_type == 'single_layer':
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')
        if self.baroclinic:
            self.add_yaml_file(
                'polaris.tasks.ocean.drying_slope', 'baroclinic.yaml'
            )
        self.add_yaml_file(
            'polaris.tasks.ocean.drying_slope', self.yaml_filename
        )

        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/initial_state.nc',
        )
        self.add_input_file(
            filename='forcing.nc', work_dir_target=f'{init.path}/forcing.nc'
        )

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'temperature',
                'salinity',
                'layerThickness',
                'normalVelocity',
            ],
        )

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

        if self.baroclinic:
            section = self.config['vertical_grid']
            vert_levels = section.getint('vert_levels')
            section = self.config['drying_slope_baroclinic']
            time_integrator = section.get('time_integrator')
            thin_film_thickness = (
                section.getfloat('min_column_thickness') / vert_levels
            )
        else:
            section = self.config['drying_slope_barotropic']
            time_integrator = section.get('time_integrator')
            thin_film_thickness = section.getfloat('thin_film_thickness')

        # dt is proportional to resolution: default 30 seconds per km
        section = self.config['drying_slope']
        if time_integrator == 'RK4':
            dt_per_km = section.getfloat('rk4_dt_per_km')
        elif time_integrator == 'split_explicit':
            dt_per_km = section.getfloat('split_dt_per_km')
            # btr_dt is also proportional to resolution
            btr_dt_per_km = section.getfloat('btr_dt_per_km')
            btr_dt = btr_dt_per_km * self.resolution
            self.btr_dt = btr_dt
        else:
            print(f'Time integrator {time_integrator} not supported')
        btr_dt_str = time.strftime('%H:%M:%S', time.gmtime(self.btr_dt))

        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        dt_str = time.strftime('%H:%M:%S', time.gmtime(dt))
        self.dt = dt

        if self.run_time_steps is not None:
            run_duration_str = time.strftime(
                '%H:%M:%S', time.gmtime(dt * self.run_time_steps)
            )
        else:
            run_duration_str = '0000_12:00:01'

        replacements = dict(
            time_integrator=time_integrator,
            dt=dt_str,
            btr_dt=btr_dt_str,
            run_duration=run_duration_str,
            hmin=f'{thin_film_thickness}',
            ramp_hmin=f'{thin_film_thickness}',
            ramp_hmax=f'{thin_film_thickness * 10.0}',
        )

        mpas_options = dict()
        if self.method == 'ramp':
            mpas_options['config_zero_drying_velocity_ramp'] = True

        mpas_options['config_implicit_bottom_drag_type'] = self.drag_type
        # for drag types not specified here, defaults are used or given in
        # forward.yaml
        if self.drag_type == 'constant':
            mpas_options['config_implicit_constant_bottom_drag_coeff'] = 3.0e-3  # type: ignore[assignment]
        elif self.drag_type == 'constant_and_rayleigh':
            # update the damping coefficient to the requested value *after*
            # loading forward.yaml
            mpas_options['config_Rayleigh_damping_coeff'] = self.damping_coeff

        forcing_dict = {
            'tidal_cycle': 'monochromatic',
            'linear_drying': 'linear',
        }

        mpas_options['config_tidal_forcing_model'] = forcing_dict[
            self.forcing_type
        ]  # type: ignore[assignment]
        if self.forcing_type == 'linear_drying':
            if self.baroclinic:
                section = self.config['drying_slope_baroclinic']
            else:
                section = self.config['drying_slope_barotropic']
            replacements['tidal_min'] = (
                section.getfloat('right_bottom_depth') + 0.5
            )
            replacements['tidal_baseline'] = section.getfloat(
                'right_tidal_height'
            )

        self.add_model_config_options(
            options=mpas_options, config_model='mpas-ocean'
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.drying_slope',
            self.yaml_filename,
            template_replacements=replacements,
        )
