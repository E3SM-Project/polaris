import os

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string

# The settings of the submesoscale eddy parameterization: off, or on with
# E3SM's coupled defaults
MLE_SETTINGS = ('off', 'on')

# The segments a run can cover: the full run, the spin-up before the eddy
# diagnosis window, the window itself (with frequent output for the eddy
# diagnostics) or the rest of the run after the window.  Each segment after
# the first continues from the restart the previous one writes at its end.
SEGMENTS = ('full', 'spinup', 'eddies', 'extended')


class Forward(OceanModelStep):
    """
    A step for performing forward ocean runs as part of mixed-layer eddies
    tasks

    Attributes
    ----------
    resolution : float
        The horizontal resolution in km

    mle : str
        The setting of the submesoscale eddy parameterization, one of
        ``MLE_SETTINGS``

    segment : str
        The segment of the run this step covers, one of ``SEGMENTS``
    """

    def __init__(
        self,
        component,
        resolution,
        init,
        name,
        subdir=None,
        indir=None,
        mle='off',
        segment='full',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The horizontal resolution in km

        init : polaris.tasks.ocean.mixed_layer_eddies.init.Init
            The step that produces the mesh and initial condition

        name : str
            The name of the step

        subdir : str, optional
            The subdirectory for the step.  If neither this nor ``indir``
            are provided, the directory is the ``name``

        indir : str, optional
            The directory the step is in, to which ``name`` will be appended

        mle : str, optional
            The setting of the submesoscale eddy parameterization, one of
            ``MLE_SETTINGS``

        segment : str, optional
            The segment of the run this step covers, one of ``SEGMENTS``
        """
        if mle not in MLE_SETTINGS:
            raise ValueError(f'Unexpected parameterization setting: {mle}')
        if segment not in SEGMENTS:
            raise ValueError(f'Unexpected run segment: {segment}')

        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            openmp_threads=1,
            update_eos=True,
            graph_target=f'{init.path}/culled_graph.info',
        )
        self.resolution = resolution
        self.mle = mle
        self.segment = segment

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_horiz_mesh_input_file(
            work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(work_dir_target=f'{init.path}/init.nc')

        self.add_output_file(filename='output.nc', validate_class='state')
        if segment == 'eddies':
            self.add_output_file(filename='eddy_output.nc')

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
        Compute the approximate number of cells in the mesh, used to
        constrain resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['mixed_layer_eddies']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        return nx * ny

    def dynamic_model_config(self, at_setup):
        """
        Add model config options and the yaml file, which depend on config
        options

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        config = self.config
        model = config.get('ocean', 'model')
        section = config['mixed_layer_eddies_forward']
        resolution = self.resolution

        time_integrator = section.get('time_integrator')
        if model == 'omega':
            time_integrator_map = dict(
                [
                    ('RK4', 'RungeKutta4'),
                    ('split_explicit', 'SplitExplicitRK2'),
                ]
            )
            time_integrator = time_integrator_map[time_integrator]

        run_duration = section.getfloat('run_duration')
        spinup_duration = section.getfloat('spinup_duration')
        window_end = spinup_duration + section.getfloat('eddy_window_duration')
        segment_bounds = dict(
            full=(0.0, run_duration),
            spinup=(0.0, spinup_duration),
            eddies=(spinup_duration, window_end),
            extended=(window_end, run_duration),
        )
        start_day, end_day = segment_bounds[self.segment]
        run_days = end_day - start_day
        write_restart = self.segment in ('spinup', 'eddies')
        do_restart = self.segment in ('eddies', 'extended')

        dt = section.getfloat('dt_per_km') * resolution
        btr_dt = section.getfloat('btr_dt_per_km') * resolution
        nu2 = section.getfloat('del2_viscosity_per_km') * resolution
        nu4 = section.getfloat('del4_viscosity_per_km3') * resolution**3

        start_time = f'0001-01-{1 + int(start_day):02d}_00:00:00'
        ocean_options = {
            'config_start_time': start_time,
            'config_run_duration': get_time_interval_string(days=run_days),
            'config_dt': get_time_interval_string(seconds=dt),
            'config_btr_dt': get_time_interval_string(seconds=btr_dt),
            'config_mom_del2': nu2,
            'config_mom_del4': nu4,
        }
        ocean_options.update(self._get_mle_options())
        self.add_model_config_options(
            options=ocean_options, config_model='ocean'
        )

        self.add_model_config_options(
            options={'config_do_restart': do_restart},
            config_model='mpas-ocean',
        )

        # restarts go one level up from the step, where the run that
        # continues from them can find them
        restart_dir = os.path.abspath(
            os.path.join(self.work_dir, '..', 'restarts')
        )
        if at_setup and (write_restart or do_restart):
            os.makedirs(restart_dir, exist_ok=True)
        restart_filename = f'{restart_dir}/ocn.rst.$Y-$M-$D_$h.$m.$s.nc'

        eddy_interval_hours = section.getfloat('eddy_output_interval')

        replacements = dict(
            time_integrator=time_integrator,
            start_time=start_time,
            start_type='Continue' if do_restart else 'StartUp',
            init_freq='never' if do_restart else 'OnStartup',
            restart_filename=restart_filename,
            restart_interval=(
                get_time_interval_string(days=run_days)
                if write_restart
                else 'none'
            ),
            restart_freq=f'{int(run_days)}',
            restart_freq_units='days' if write_restart else 'never',
            mle=self.mle != 'off',
            eddy_output=self.segment == 'eddies',
            eddy_output_interval=get_time_interval_string(
                seconds=3600.0 * eddy_interval_hours
            ),
            eddy_output_freq=f'{int(eddy_interval_hours)}',
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.mixed_layer_eddies',
            'forward.yaml',
            template_replacements=replacements,
        )

    def _get_mle_options(self):
        """
        Get the options for the submesoscale eddy parameterization.  When it
        is off, none are set, so each model's default (off) applies.
        """
        if self.mle == 'off':
            return {}
        section = self.config['mixed_layer_eddies_mle']
        return {
            'config_submesoscale_enable': True,
            'config_submesoscale_tau': section.getfloat('tau'),
            'config_submesoscale_Ce': section.getfloat('ce'),
            'config_submesoscale_Lfmin': section.getfloat('lf_min'),
            'config_submesoscale_ds_max': section.getfloat('ds_max'),
        }
