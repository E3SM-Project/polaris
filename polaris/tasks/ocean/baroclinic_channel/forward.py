import os
import time

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
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        nu=10.0,
        run_time_steps=None,
        start_time_steps=None,
        graph_target='graph.info',
        do_restart=False,
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

        nu : float, optional
            the viscosity (if different from the default for baroclinic channel
            tests)

        run_time_steps : int, optional
            Number of time steps to run for

        start_time_steps : int, optional
            Number of time steps to start from

        graph_target : str, optional
            The graph file name (relative to the base work directory).
            If none, it will be created.
        """
        self.do_restart = do_restart
        self.resolution = resolution
        self.run_time_steps = run_time_steps
        self.start_time_steps = start_time_steps
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

        self.add_horiz_mesh_input_file(target='../../init/culled_mesh.nc')
        self.add_vert_coord_input_file(target='../../init/vert_coord.nc')
        self.add_init_input_file(target='../../init/init.nc')

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
        self.nu = nu

    def setup(self):
        """
        Set up the step, adding the OmegaMesh.nc symlink for Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['baroclinic_channel']
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
        model = config.get('ocean', 'model')

        time_integrator = config.get('baroclinic_channel', 'time_integrator')
        time_integrator_map = dict([('RK4', 'RungeKutta4')])
        if model == 'omega':
            if time_integrator in time_integrator_map.keys():
                time_integrator = time_integrator_map[time_integrator]
            else:
                print(
                    'Warning: mapping from time integrator '
                    f'{time_integrator} to omega not found, '
                    'retaining name given in config'
                )

        # dt is proportional to resolution: default 30 seconds per km
        dt_per_km = config.getfloat('baroclinic_channel', 'dt_per_km')
        dt = dt_per_km * self.resolution
        dt_str = get_time_interval_string(seconds=dt)

        # btr_dt is only for MPAS-Ocean (Omega uses RK4)
        btr_dt_per_km = config.getfloat('baroclinic_channel', 'btr_dt_per_km')
        btr_dt = btr_dt_per_km * self.resolution
        mpaso_options = {
            'config_btr_dt': time.strftime('%H:%M:%S', time.gmtime(btr_dt))
        }

        # Set dt and default run duration, which may be changed below
        ocean_options = {
            'config_dt': dt_str,
        }

        start_str = '0001-01-01_00:00:00'
        if self.start_time_steps is not None:
            start_seconds = self.start_time_steps * dt
            start_str = get_time_interval_string(seconds=start_seconds)
            # Assume the default start time for the full_run
            start_str = f'0001-01-01_{start_str.split("_")[1]}'
            ocean_options['config_start_time'] = start_str
            mpaso_options['config_do_restart'] = 'True'

        if self.name == 'long_forward':
            run_duration = config.getfloat(
                'baroclinic_channel_long', 'run_duration'
            )
            run_duration_str = get_time_interval_string(days=run_duration)
            output_freq = config.getfloat(
                'baroclinic_channel_long', 'output_interval'
            )
            output_freq_units = config.get(
                'baroclinic_channel_long', 'output_interval_units'
            )
            output_freq = int(output_freq)
        elif self.nu is not None:  # an indication of an rpe test step
            run_duration = config.getfloat(
                'baroclinic_channel_rpe', 'run_duration'
            )
            run_duration_str = get_time_interval_string(days=run_duration)
            output_freq = 1
            output_freq_units = 'days'
        elif self.run_time_steps is not None:
            run_seconds = self.run_time_steps * dt
            run_duration_str = get_time_interval_string(seconds=run_seconds)
            output_freq = int(run_seconds)
            output_freq_units = 'seconds'
        else:
            raise ValueError(
                'Could not determine run duration and output frequency for run'
            )
        ocean_options['config_run_duration'] = run_duration_str

        # Get output interval for mpas-ocean
        if model == 'mpas-ocean':
            if output_freq_units == 'seconds':
                seconds = output_freq
            if output_freq_units == 'minutes':
                seconds = output_freq * 60
            elif output_freq_units == 'hours':
                seconds = output_freq * 3600
            elif output_freq_units == 'days':
                seconds = output_freq * 86400
            else:
                raise ValueError(
                    'Warning: output frequency units '
                    f'{output_freq_units} not supported'
                )
                seconds = 1.0
            output_interval = get_time_interval_string(seconds=seconds)
        else:
            output_interval = ''

        # restart units are set to seconds below
        if self.start_time_steps is not None:
            restart_interval = dt_str
            restart_freq = int(dt)
        else:
            restart_interval = get_time_interval_string(days=1)
            restart_freq = int(24 * 3600)

        if self.do_restart:
            init_freq = 'never'
            restart_start_time = start_str
            # We store restarts one level up from the step to be easily
            # accessed by multiple steps
            restart_dir = os.path.abspath(
                os.path.join(self.work_dir, '..', 'restarts')
            )
            os.makedirs(restart_dir, exist_ok=True)
            restart_filename = f'{restart_dir}/ocn.rst.$Y-$M-$D_$h.$m.$s'
        else:
            init_freq = 'OnStartup'
            restart_filename = 'ocn.rst.$Y-$M-$D_$h.$m.$s'
            # The restart start time must be >= simulation start time
            restart_start_time = '0001-01-01_00:00:01'

        if self.nu is not None:
            # update the viscosity to the requested value *after* loading
            # forward.yaml
            ocean_options['config_mom_del2'] = self.nu

        self.add_model_config_options(
            options=ocean_options, config_model='ocean'
        )
        self.add_model_config_options(
            options=mpaso_options, config_model='mpas-ocean'
        )

        replacements = dict(
            init_freq=init_freq,
            restart_filename=restart_filename,
            restart_start_time=restart_start_time,
            not_restart=not self.do_restart,
            output_freq=f'{output_freq}',
            output_freq_units=output_freq_units,
            time_integrator=time_integrator,
            output_interval=output_interval,
            restart_interval=restart_interval,
            restart_freq=restart_freq,
            restart_freq_units='seconds',
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.baroclinic_channel',
            'forward.yaml',
            template_replacements=replacements,
        )
