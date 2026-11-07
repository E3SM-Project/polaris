import importlib.resources as imp_res
import os
import re
import shutil
import textwrap
from collections import namedtuple

import yaml
from jinja2 import Template
from mpas_tools.io import open_dataset

import polaris.namelist
from polaris.config import PolarisConfigParser
from polaris.e3sm.init import inputdata
from polaris.e3sm.init.partitions import get_core_list
from polaris.landice.mismip_plus.geometry import ICE_DENSITY, OCEAN_DENSITY
from polaris.mpas.time import duration_to_seconds
from polaris.step import Step
from polaris.tasks.e3sm.init.misomip import names
from polaris.tasks.e3sm.init.misomip.landice_data import (
    DATA_MODE_EXPERIMENTS,
)
from polaris.tasks.e3sm.init.misomip.landice_init import CONTINUES_FROM
from polaris.tasks.e3sm.init.misomip.layout import (
    get_layout,
    get_layout_lines,
    get_task_bounds,
)
from polaris.tasks.e3sm.init.misomip.records import get_monthly_record_times
from polaris.tasks.landice.mismip_plus.forward import MALI_DYNAMIC_THICKNESS

#: The section of config options for the case configuration
CASE_CONFIG_SECTION = 'misomip_case_config'

#: E3SM's inputdata directory, as a case variable that CIME expands
DIN_LOC_ROOT = '$DIN_LOC_ROOT'

#: The length of each experiment in months, as the protocols prescribe,
#: except Ocean0, which runs three years rather than one because at 2 km it
#: settles only in its third year
RUN_MONTHS = {
    'ocean0': 36,
    'ocean1': 240,
    'ocean2': 240,
    'ocean3': 1200,
    'ocean4': 1200,
    'iceocean1r': 1200,
    'iceocean1ra': 1200,
}

#: The length in months of the long runs, whose jobs run
#: ``[misomip_case_config] long_run_months_per_job`` and whose last year has
#: daily means of 3D fields
LONG_RUN_MONTHS = 1200

#: The months between restarts, a divisor of every job's months
RESTART_MONTHS = 12

#: The months at the start of every run, and at the end of a long one, with
#: daily means of :py:data:`DAILY_3D_OCEAN_FIELDS`
DAILY_3D_MONTHS = 12

#: The length in months of a run short enough to have daily means of 3D
#: fields throughout, which includes Ocean0
DAILY_3D_WHOLE_RUN_MONTHS = 36

#: A segment of a run: the months run before it, its months and whether the
#: ocean writes daily means of 3D fields
Segment = namedtuple('Segment', ['start', 'months', 'daily_3d'])

#: The experiments in which MALI is prognostic, with Albany's first-order
#: velocity solver
PROGNOSTIC_EXPERIMENTS = ['iceocean1r', 'iceocean1ra']

#: The commit of FAnSSIE, E3SM's development branch for coupling the ocean
#: and ice sheets, by which it has every change the cases need: the last is
#: MALI's rebuild of Albany's finite-element grid only when its masks
#: change, without which a multi-year job grows and slows
E3SM_COMMIT = '5eb5f0385b'

#: The change the split-explicit cases need that FAnSSIE does not have yet:
#: the ocean's per-layer limit on drying, which has no namelist option, so
#: no script can check for it
SPLIT_EXPLICIT_PENDING = 'E3SM-Ocean-Discussion/E3SM#175'

#: The ocean's time integrators a case configuration can have
TIME_INTEGRATORS = ['RK4', 'split_explicit']

#: The YAML files of MPAS-Ocean options the standalone run of each time
#: integrator adds, by package and file name.  An MPAS-Ocean build older
#: than an option leaves it out of the namelist it renders, with only a
#: warning at setup.
INTEGRATOR_YAML_FILES = {
    'RK4': [],
    'split_explicit': [
        ('polaris.tasks.ocean.isomip_plus', 'split_explicit.yaml'),
    ],
}

#: The compset of each mode of MALI, by long name
COMPSETS = {
    'static': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV',
    'data': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIADATA_SWAV',
    'prognostic': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI_SWAV',
}

#: MPAS-Ocean namelist groups whose options a standalone run sets but an
#: E3SM case leaves to E3SM: the run's times, I/O, partitions and the
#: standalone land-ice forcing, which the coupler replaces.  Of each
#: analysis member's group, only whether it is on is written, since E3SM
#: configures the members' output.
STANDALONE_GROUPS = [
    'time_management',
    'io',
    'decomposition',
    'time_varying_forcing',
]

#: MPAS-Ocean options whose E3SM default differs from MPAS-Ocean's own, or
#: that E3SM gives a default only for the grids it lists.  Some come from
#: E3SM's namelist defaults and some from its namelist builder, which sets
#: the tidal velocity of the melt parameterization from a case variable.
#: Each is written with the standalone run's value, so the E3SM case has the
#: standalone run's physics even where that is MPAS-Ocean's default.
E3SM_DEFAULT_OPTIONS = [
    # E3SM's defaults only for the grids it lists
    'config_dt',
    'config_hmix_scaleWithMesh',
    'config_mom_del4',
    # E3SM's defaults differ
    'config_cvmix_background_diffusion',
    'config_cvmix_background_diffusion_passive',
    'config_cvmix_shear_mixing_scheme',
    'config_enable_shortwave_energy_fixer',
    'config_eos_type',
    'config_flux_attenuation_coefficient_runoff',
    'config_frazil_heat_of_fusion',
    'config_frazil_use_surface_pressure',
    'config_GM_constant_kappa',
    'config_GM_geometric_backgroundEddyEnergy',
    'config_GM_spatially_variable_baroclinic_mode',
    'config_GM_Visbeck_alpha',
    'config_implicit_top_drag_coeff',
    'config_include_KE_vertex',
    'config_mom_del2',
    'config_parallel_self_attraction_loading_bfb',
    'config_precip_scaling_mode',
    'config_pressure_gradient_type',
    'config_Rayleigh_damping_coeff',
    'config_Redi_constant_kappa',
    'config_Redi_maximum_slope',
    'config_Redi_min_layers_diag_terms',
    'config_salinity_restoring_constant_piston_velocity',
    'config_salinity_restoring_max_difference',
    'config_salinity_restoring_under_sea_ice',
    'config_specific_heat_sea_water',
    'config_submesoscale_Ce',
    'config_submesoscale_enable',
    'config_sw_absorption_type',
    'config_topographic_wave_drag_coeff',
    'config_use_activeTracers_surface_bulk_forcing',
    'config_use_bulk_thickness_flux',
    'config_use_cvmix_convection',
    'config_use_cvmix_kpp',
    'config_use_cvmix_shear',
    'config_use_frazil_ice_formation',
    'config_use_GM',
    'config_use_mom_del4',
    'config_use_Redi',
    # set by E3SM's namelist builder
    'config_land_ice_flux_tidal_Jourdain_alpha',
    'config_land_ice_flux_tidal_Jourdain_A0',
    'config_land_ice_flux_tidal_Jourdain_U0',
]

#: MPAS-Ocean options that keep E3SM's values, though they differ from the
#: standalone run's: E3SM's ocean takes the coupler's wind stress through its
#: bulk forcing, so turning it off breaks the time step
E3SM_OWNED_OPTIONS = [
    'config_use_bulk_wind_stress',
    'config_bulk_wind_stress_interp_isotropic',
]

#: MPAS-Ocean options an E3SM case sets that a standalone run has no use for
E3SM_OCEAN_OPTIONS = {
    # MALI's geometry replaces the ocean's at every coupling step
    'config_glc_ice_shelf_coupling_import_geometry': '.true.',
}

#: The MPAS-Ocean option that turns on the daily means
DAILY_SWITCH = 'config_AM_timeSeriesStatsDaily_enable'

#: The MPAS-Ocean option with the interval between the daily means'
#: samples, every time step in place of E3SM's hourly samples, which alias
#: fast changes in the melt.  E3SM's monthly means already sample every
#: time step.
DAILY_COMPUTE_INTERVAL = 'config_AM_timeSeriesStatsDaily_compute_interval'

#: The MPAS-Ocean option with the land-ice fraction at or below which the
#: import of MALI's geometry leaves a cell open ocean, written from
#: ``[misomip_land_ice_on_ocean] min_land_ice_fraction``, so the initial
#: conditions and the imports agree
MIN_FRACTION_OPTION = 'config_glc_ice_shelf_coupling_min_floating_fraction'

#: The MPAS-Ocean option that ramps the land-ice pressure from MALI over
#: each of MALI's coupling intervals, for a case whose MALI geometry
#: changes.  E3SM sets the interval from the case's coupling.
RAMP_OPTION = 'config_glc_ice_shelf_coupling_ramp_land_ice_pressure'

#: MALI options an E3SM case sets.  The densities are those the ocean's
#: initial condition used for the land-ice pressure.  Building Albany's
#: finite-element grid once avoids a leak at every rebuild.
MALI_OPTIONS = {
    'config_ice_density': repr(ICE_DENSITY),
    'config_ocean_density': repr(OCEAN_DENSITY),
    'config_always_compute_fem_grid': '.false.',
}

#: The directory of the user-mods files, relative to the step's work
#: directory
USER_MODS = 'user_mods'

#: The script that creates, sets up and builds a case
CREATE_CASE = 'create_case.sh'

#: The case's layout, which the script gives ``create_newcase``
PES = 'pes.xml'

#: The MISMIP+ tasks' Albany input, which a prognostic MALI reads
ALBANY_INPUT = 'albany_input.yaml'

#: Where in the user-mods directory MALI's source modifications go, which
#: CIME copies to the case's
MALI_SOURCE_MODS = os.path.join('SourceMods', 'src.mali')

#: The script with which ``create_case.sh`` adds a case's output to the
#: streams files E3SM writes
EDIT_STREAMS = 'edit_streams.py'

#: The script that sets up each segment of a case, which CIME runs after
#: each job
NEXT_SEGMENT = 'next_segment.sh'

#: The directory in the case directory with the ocean's streams files with
#: and without daily means of 3D fields, from which ``next_segment.sh``
#: copies one into SourceMods
OCEAN_STREAMS_DIR = 'ocean_streams'

#: What the step writes that is staged: the user-mods directory, and the
#: README, scripts and layout beside it
CASE_CONFIG_FILES = [
    USER_MODS,
    'README',
    CREATE_CASE,
    PES,
    EDIT_STREAMS,
    NEXT_SEGMENT,
]

#: The ocean's daily means in every case, in place of E3SM's daily list:
#: the melt and freezing fluxes, and the part of the melt not sent to MALI,
#: from which the melt exchange can be checked day by day
DAILY_OCEAN_FIELDS = [
    'landIceFreshwaterFlux',
    'frazilIceFreshwaterFlux',
    'landIceFreshwaterFluxNotSentToGlc',
    'landIceHeatFlux',
]

#: The 3D fields added to the ocean's daily means in the segments with
#: them (:py:func:`get_segments`): the state, and the layer thickness and
#: the thickness frazil formation applies, from which the ocean's volume
#: budget estimates the transport across edges.  ``activeTracers`` is a
#: variable array.
DAILY_3D_OCEAN_FIELDS = [
    'normalVelocity',
    'layerThickness',
    'activeTracers',
    'frazilLayerThicknessTendency',
]

#: The variable arrays among the ocean's daily fields
OCEAN_VAR_ARRAYS = ['activeTracers']

#: Fields added to the ocean's monthly means in every case, which already
#: hold the layer thickness and its frazil tendency: the part of the melt not
#: sent to MALI, and the vertical transport through each layer's top
#: interface, whose monthly mean is exact where the product of the monthly
#: means of velocity and thickness is not, from which the overturning
#: streamfunction follows with the snapshots of the layer thickness, the
#: vertical velocity relative to fixed heights, from which the overturning
#: streamfunction in height follows column by column, and the thickness flux
#: the time integrator applies across each edge, whose monthly mean gives
#: the transport exactly, a check on the others
MONTHLY_OCEAN_FIELDS = [
    'landIceFreshwaterFluxNotSentToGlc',
    'vertAleTransportTop',
    'vertVelocityTop',
    'normalLayerThicknessFlux',
]

#: MPAS-Ocean options of every case for its overturning streamfunction:
#: computing the thickness flux the time integrator applies, which is off
#: by default
OVERTURNING_OPTIONS = {
    'config_compute_normal_layer_thickness_flux': '.true.',
}

#: The stream of snapshots of the ocean's layer thickness at the start of
#: each month, whose change over a month is the volume each layer gains,
#: the fields in it, and its interval
SNAPSHOT_STREAM = 'layerThicknessSnapshotOutput'
SNAPSHOT_OCEAN_FIELDS = ['layerThickness']
SNAPSHOT_INTERVAL = '00-01-00_00:00:00'

#: MPAS-Ocean options of every case that monitor the ocean: the global
#: statistics, written hourly by the streams edit, and the daily maximum of
#: :py:data:`DAILY_MAX_OCEAN_FIELDS` with the custom time series, checked
#: every time step, which catches a short burst that daily means smooth
#: out
MONITORING_OPTIONS = {
    'config_AM_globalStats_enable': '.true.',
    'config_AM_timeSeriesStatsCustom_enable': '.true.',
    'config_AM_timeSeriesStatsCustom_operation': "'max'",
    'config_AM_timeSeriesStatsCustom_compute_interval': "'dt'",
    'config_AM_timeSeriesStatsCustom_reset_intervals': "'00-00-01_00:00:00'",
}

#: The ocean's daily maxima in every case, in place of E3SM's list for the
#: custom time series
DAILY_MAX_OCEAN_FIELDS = ['kineticEnergyCell']

#: The interval of the ocean's global statistics in every case
GLOBAL_STATS_INTERVAL = '0000-00-00_01:00:00'

#: The interval of the ocean's daily maxima
DAILY_MAX_INTERVAL = '0000-00-01_00:00:00'

#: The interval of MALI's history in a case with a prognostic MALI, a month
#: so that it aligns with the ocean's monthly means
MALI_HISTORY_INTERVAL = '0000-01-00_00:00:00'

#: Fields added to MALI's history in a case with a prognostic MALI, besides
#: those of the MISMIP+ tasks' output: the mesh the MISMIP+ diagnostics
#: read, and the melt MALI applies, averaged over the interval
MALI_HISTORY_FIELDS = [
    'xCell',
    'yCell',
    'areaCell',
    'dcEdge',
    'avgFloatingBMBFlux',
]

#: MALI's daily output in a case with a prognostic MALI: the melt the
#: ocean sends and the melt MALI applies
MALI_DAILY_FIELDS = ['floatingBasalMassBal', 'floatingBasalMassBalApplied']

#: MALI options whose E3SM default differs from MALI's own, which the
#: MISMIP+ tasks run with, written for a prognostic MALI with MALI's
#: values: no thermal solver or tracer advection, no ISMIP6 melt or face
#: melt, the calving options' MALI defaults, and no regional statistics,
#: which need region masks the cases lack
MALI_E3SM_DEFAULT_OPTIONS = {
    'config_thermal_solver': "'none'",
    'config_tracer_advection': "'none'",
    'config_front_mass_bal_grounded': "'none'",
    'config_use_3d_thermal_forcing_for_face_melt': '.false.',
    'config_ocean_data_extrapolation': '.false.',
    'config_calving_error_threshold': '0.1',
    'config_crevasse_water_depth': '0.0',
    'config_distribute_unablatedVolumeDynCell': '.false.',
    'config_restore_calving_front_prevent_retreat': '.true.',
    'config_AM_regionalStats_enable': '.false.',
}

#: MALI options whose E3SM default differs from MALI's own that keep E3SM's
#: value, with the reason
MALI_E3SM_OWNED_OPTIONS = {
    # the first-order solver is the point of a prognostic MALI
    'config_velocity_solver': 'Albany',
    # the melt under floating ice comes from the ocean
    'config_basal_mass_bal_float': 'coupling',
    # MALI's time step follows its coupling, and the 1-hour floor is far
    # below its CFL limit on the 1 km mesh
    'config_dt': 'coupling',
    'config_adaptive_timestep_force_interval': 'coupling',
    'config_min_adaptive_timestep': 'coupling',
    # E3SM's run control, files and calendar
    'config_restart_timestamp_name': 'E3SM',
    'config_calendar_type': 'E3SM',
    'config_block_decomp_file_prefix': 'E3SM',
    'config_proc_decomp_file_prefix': 'E3SM',
    # E3SM's SMB source is set from the case; the cases read the file's
    'config_smb_source': 'E3SM',
    # the global statistics, on as in the MISMIP+ tasks, with E3SM's output
    'config_AM_globalStats_enable': 'output',
    'config_AM_globalStats_compute_interval': 'output',
}

#: Options of the MISMIP+ tasks' MALI namelist that an E3SM case leaves to
#: E3SM: the run's start, the partition files and the analysis members,
#: whose output E3SM configures
MISMIP_PLUS_STANDALONE_OPTIONS = [
    'config_start_time',
    'config_year_digits',
    'config_block_decomp_file_prefix',
    'config_AM_globalStats_enable',
    'config_AM_globalStats_compute_interval',
    'config_AM_globalStats_compute_on_startup',
    'config_AM_globalStats_write_on_startup',
]

#: The components of an MCT case, each with a task count in the layout
COMPONENTS = ['atm', 'lnd', 'rof', 'ice', 'ocn', 'glc', 'wav', 'cpl']

#: The config section of each mesh's graph partitions, which also has the
#: goal cells per task of a case
PARTITION_SECTIONS = {
    'ocean': 'misomip_ocean_partitions',
    'landice': 'misomip_landice_partitions',
}

#: The name of each model in a description of the layout
MODEL_NAMES = {'ocean': 'the ocean', 'landice': 'MALI'}


class CaseConfigStep(Step):
    """
    A step for writing the E3SM case configuration of one MISOMIP
    experiment: a user-mods directory, with the grid file, a README with
    the compset and a script that creates a case

    Attributes
    ----------
    experiment : str
        The experiment
    """

    def __init__(
        self,
        component,
        subdir,
        experiment,
        mesh_steps,
        forward_step,
        ocean_config_filepath,
        time_integrator='RK4',
        name='case_config',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        experiment : str
            The experiment, one of :py:data:`RUN_MONTHS`

        mesh_steps : dict of str to polaris.Step
            The steps that wrote the ``ocean`` and ``landice`` SCRIP files

        forward_step : polaris.Step
            The standalone MPAS-Ocean run, whose namelist holds the options
            the E3SM case shares.  For an experiment that continues from
            another, it is the other experiment's.

        ocean_config_filepath : str
            The config file of the experiment's ocean steps, relative to the
            base work directory, which says where MPAS-Ocean's default
            namelist is

        time_integrator : str, optional
            The standalone run's time integrator, one of
            :py:data:`TIME_INTEGRATORS`

        name : str, optional
            The name of the step, unique among the task's steps
        """
        if time_integrator not in TIME_INTEGRATORS:
            raise ValueError(
                f'No E3SM case configuration with the time integrator '
                f'{time_integrator}.'
            )
        if experiment not in RUN_MONTHS:
            raise ValueError(
                f'No E3SM case configuration for experiment {experiment}.'
            )
        super().__init__(component=component, name=name, subdir=subdir)
        self.experiment = experiment
        self.time_integrator = time_integrator
        self.add_input_file(
            filename='ocean_scrip.nc',
            work_dir_target=os.path.join(
                mesh_steps['ocean'].path, 'ocean_scrip.nc'
            ),
        )
        self.add_input_file(
            filename='landice_scrip.nc',
            work_dir_target=os.path.join(
                mesh_steps['landice'].path, 'landice_scrip.nc'
            ),
        )
        self.add_input_file(
            filename='namelist.ocean',
            work_dir_target=os.path.join(forward_step.path, 'namelist.ocean'),
        )
        self.add_input_file(
            filename='ocean.cfg', work_dir_target=ocean_config_filepath
        )
        for filename in [
            'config_grids.xml',
            'shell_commands',
            'user_nl_mpaso',
            'user_nl_mali',
        ]:
            self.add_output_file(filename=os.path.join(USER_MODS, filename))
        self.add_output_file(filename='README')
        self.add_output_file(filename=CREATE_CASE)
        self.add_output_file(filename=PES)
        self.add_output_file(filename=EDIT_STREAMS)
        self.add_output_file(filename=NEXT_SEGMENT)
        if get_mali_mode(experiment) == 'prognostic':
            self.add_input_file(
                filename=ALBANY_INPUT,
                target=ALBANY_INPUT,
                package='polaris.tasks.landice.mismip_plus',
            )
            albany_input = os.path.join(
                USER_MODS, MALI_SOURCE_MODS, ALBANY_INPUT
            )
            self.add_output_file(filename=albany_input)

    def run(self):
        """
        Write the user-mods directory, the README and the script
        """
        config = self.config
        experiment = self.experiment
        prognostic = get_mali_mode(experiment) == 'prognostic'
        grids = names.get_grid_names(config)
        date = inputdata.get_creation_date(config, names.INPUTS_SECTION)
        section = config[CASE_CONFIG_SECTION]
        root = get_inputdata_root(config, experiment)
        source = CONTINUES_FROM.get(experiment)
        source_root = (
            None if source is None else get_inputdata_root(config, source)
        )
        segments = get_segments(
            experiment, get_months_per_job(config, experiment)
        )
        couplings_per_day = {
            grid: section.getint(f'{grid}_couplings_per_day')
            for grid in ['ocean', 'landice']
        }
        cell_counts = _get_cell_counts()

        ocean_config = PolarisConfigParser()
        ocean_config.add_from_file('ocean.cfg')
        defaults = polaris.namelist.ingest(
            ocean_config.get('namelists', 'forward')
        )
        standalone = polaris.namelist.ingest('namelist.ocean')
        check_time_integrator(standalone, self.time_integrator)
        dt = duration_to_seconds(
            standalone['time_integration']['config_dt'].strip('\'"')
        )

        os.makedirs(USER_MODS, exist_ok=True)
        _write(
            os.path.join(USER_MODS, 'config_grids.xml'),
            get_grid_file(grids, date, root, cell_counts),
        )
        _write(
            os.path.join(USER_MODS, 'shell_commands'),
            get_shell_commands(
                experiment,
                grids,
                date,
                root,
                segments,
                couplings_per_day,
                dt,
                source_inputdata_root=source_root,
                job_wall_time=inputdata.get_nonempty_option(
                    config, CASE_CONFIG_SECTION, 'job_wall_time'
                ),
            ),
            executable=True,
        )
        _write(
            os.path.join(USER_MODS, 'user_nl_mpaso'),
            get_user_nl_mpaso(
                standalone,
                defaults,
                config.getfloat(
                    'misomip_land_ice_on_ocean', 'min_land_ice_fraction'
                ),
                # MALI's geometry changes in data mode and when prognostic
                ramp_land_ice_pressure=get_mali_mode(self.experiment)
                != 'static',
            ),
        )
        mismip_plus_config = PolarisConfigParser()
        mismip_plus_config.add_from_package(
            'polaris.tasks.landice.mismip_plus', 'mismip_plus.cfg'
        )
        _write(
            os.path.join(USER_MODS, 'user_nl_mali'),
            get_user_nl_mali(
                experiment,
                mismip_plus_config.getfloat('mismip_plus', 'flow_param_a'),
            ),
        )
        if prognostic:
            source_mods = os.path.join(USER_MODS, MALI_SOURCE_MODS)
            os.makedirs(source_mods, exist_ok=True)
            shutil.copyfile(
                ALBANY_INPUT, os.path.join(source_mods, ALBANY_INPUT)
            )
        _write(
            EDIT_STREAMS,
            get_edit_streams_script(experiment),
            executable=True,
        )
        _write(
            NEXT_SEGMENT,
            get_next_segment_script(experiment, segments),
            executable=True,
        )
        task_counts = {
            grid: [
                int(count)
                for count in get_core_list(
                    ncells=cell_counts[grid],
                    max_cells_per_core=config.getint(
                        PARTITION_SECTIONS[grid], 'max_cells_per_core'
                    ),
                    min_cells_per_core=config.getint(
                        PARTITION_SECTIONS[grid], 'min_cells_per_core'
                    ),
                )
            ]
            for grid in PARTITION_SECTIONS
        }
        layout, cells_per_task = self._get_layout(cell_counts, task_counts)
        machine = get_machine(config)
        layout_lines = get_layout_lines(layout, cells_per_task, machine)
        for line in layout_lines:
            self.logger.info(line)
        _write(
            'README',
            get_readme(
                experiment,
                grids,
                layout_lines,
                self.time_integrator,
                segments=segments,
            ),
        )
        _write(
            CREATE_CASE,
            get_create_case_script(
                experiment,
                grids,
                task_counts,
                layout,
                machine,
                config.get('build', 'compiler'),
            ),
            executable=True,
        )
        _write(PES, get_pes_file(layout))

    def _get_layout(self, cell_counts, task_counts):
        """
        Get the case's layout from each model's cells per task and the
        machine's parallel system.  MALI's cells per task limit the tasks
        only when it is prognostic.
        """
        config = self.config
        grids = ['ocean']
        if get_mali_mode(self.experiment) == 'prognostic':
            grids.append('landice')
        cells_per_task = dict()
        model_bounds = list()
        for grid in grids:
            section = config[PARTITION_SECTIONS[grid]]
            option = inputdata.get_nonempty_option(
                config, PARTITION_SECTIONS[grid], 'goal_cells_per_core'
            )
            goal = None if option is None else float(option)
            low = section.getfloat('min_cells_per_core')
            high = section.getfloat('max_cells_per_core')
            cells_per_task[MODEL_NAMES[grid]] = (goal, low, high)
            # without a goal, only the model's bounds apply: its target is
            # its most tasks, so another model's target sets the tasks
            model_bounds.append(
                get_task_bounds(
                    cell_counts[grid], low if goal is None else goal, low, high
                )
            )

        # a batch system's node, not the cores of wherever the step runs,
        # such as a login node
        batch = config.get('parallel', 'system') != 'single_node'
        if batch:
            tasks_per_node = config.getint('parallel', 'cores_per_node')
        else:
            parallel_system = self.component.parallel_system
            assert parallel_system is not None
            tasks_per_node = parallel_system.cores_per_node
        if config.has_option('parallel', 'max_mpi_tasks_per_node'):
            tasks_per_node = min(
                tasks_per_node,
                config.getint('parallel', 'max_mpi_tasks_per_node'),
            )
        partitions = sorted(
            set(task_counts['ocean']) & set(task_counts['landice'])
        )
        layout = get_layout(model_bounds, tasks_per_node, batch, partitions)
        return layout, cells_per_task


def get_machine(config):
    """
    Get the machine Polaris was set up on, from ``[build] machine``

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The step's config options

    Returns
    -------
    machine : str
        The machine, or an empty string if Polaris has no name for it
    """
    machine = config.get('build', 'machine')
    return '' if machine == 'default' else machine


def get_mali_mode(experiment):
    """
    Get the mode MALI runs in for an experiment

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    mode : {'static', 'data', 'prognostic'}
        The mode, a key of :py:data:`COMPSETS`
    """
    if experiment in PROGNOSTIC_EXPERIMENTS:
        return 'prognostic'
    return 'data' if experiment in DATA_MODE_EXPERIMENTS else 'static'


def get_months_per_job(config, experiment):
    """
    Get the most months a job of an experiment's case runs, from
    ``[misomip_case_config] long_run_months_per_job`` for a run of
    :py:data:`LONG_RUN_MONTHS` and ``short_run_months_per_job`` for a shorter
    one

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The step's config options

    experiment : str
        The experiment

    Returns
    -------
    months_per_job : int
        The most months a job runs
    """
    length = 'long' if RUN_MONTHS[experiment] >= LONG_RUN_MONTHS else 'short'
    return config.getint(CASE_CONFIG_SECTION, f'{length}_run_months_per_job')


def get_daily_3d_windows(experiment):
    """
    Get the months of an experiment's run with daily means of
    :py:data:`DAILY_3D_OCEAN_FIELDS`: the first year, the last year of a
    long run, and all of a run of :py:data:`DAILY_3D_WHOLE_RUN_MONTHS` or
    fewer

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    windows : list of tuple of int
        The months run before each window starts and ends
    """
    months = RUN_MONTHS[experiment]
    if months <= DAILY_3D_WHOLE_RUN_MONTHS:
        return [(0, months)]
    windows = [(0, DAILY_3D_MONTHS)]
    if months >= LONG_RUN_MONTHS:
        windows.append((months - DAILY_3D_MONTHS, months))
    return windows


def get_segments(experiment, months_per_job):
    """
    Get the segments an experiment's case runs in, one a job.  Each runs
    ``months_per_job`` months, or fewer where it must end at the start or
    end of a window with daily means of 3D fields
    (:py:func:`get_daily_3d_windows`), so each segment is wholly in or out
    of one.

    Parameters
    ----------
    experiment : str
        The experiment

    months_per_job : int
        The most months a job runs, a multiple of
        :py:data:`RESTART_MONTHS`

    Returns
    -------
    segments : list of Segment
        The segments, in order
    """
    if months_per_job <= 0 or months_per_job % RESTART_MONTHS != 0:
        raise ValueError(
            f'A job runs {months_per_job} months, not a multiple of the '
            f'{RESTART_MONTHS} months between restarts.'
        )
    months = RUN_MONTHS[experiment]
    windows = get_daily_3d_windows(experiment)
    bounds = sorted(
        {0, months} | {edge for window in windows for edge in window}
    )
    segments = list()
    for begin, end in zip(bounds[:-1], bounds[1:], strict=True):
        daily_3d = any(first <= begin < last for first, last in windows)
        start = begin
        while start < end:
            length = min(months_per_job, end - start)
            segments.append(Segment(start, length, daily_3d))
            start += length
    return segments


def check_time_integrator(standalone, time_integrator):
    """
    Check that the standalone run's namelist has the case's time integrator
    and every option the integrator's YAML files add, which an MPAS-Ocean
    build older than an option leaves out

    Parameters
    ----------
    standalone : dict
        The standalone run's namelist, as :py:func:`polaris.namelist.ingest`
        reads it

    time_integrator : str
        The case's time integrator, one of :py:data:`TIME_INTEGRATORS`

    Raises
    ------
    ValueError
        If the namelist has another time integrator or lacks an option
    """
    options = {
        option: value
        for group in standalone.values()
        for option, value in group.items()
    }
    found = options.get('config_time_integrator', '').strip('\'"')
    if found != time_integrator:
        raise ValueError(
            f'The standalone namelist has the time integrator {found}, not '
            f'{time_integrator}.'
        )
    missing: list[str] = list()
    for package, filename in INTEGRATOR_YAML_FILES[time_integrator]:
        text = imp_res.files(package).joinpath(filename).read_text()
        for group in yaml.safe_load(text)['mpas-ocean'].values():
            missing.extend(option for option in group if option not in options)
    if missing:
        raise ValueError(
            f'The standalone namelist lacks {", ".join(sorted(missing))}. '
            f'Set the task up with an MPAS-Ocean build that has them.'
        )


def get_case_config_files(experiment):
    """
    Get what the case configuration step writes that is staged for an
    experiment

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    filenames : list of str
        :py:data:`CASE_CONFIG_FILES`
    """
    return list(CASE_CONFIG_FILES)


def get_inputdata_root(config, experiment):
    """
    Get where an experiment's case finds the staged files, from
    ``[misomip_case_config] inputdata_root``, with ``{experiment}`` replaced
    by the experiment's name

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options of the pair of meshes

    experiment : str
        The experiment

    Returns
    -------
    inputdata_root : str
        :py:data:`DIN_LOC_ROOT` if the option is blank, or the directory
    """
    root = inputdata.get_nonempty_option(
        config, CASE_CONFIG_SECTION, 'inputdata_root'
    )
    if root is None:
        return DIN_LOC_ROOT
    return root.replace('{experiment}', experiment)


def get_grid_file(grids, creation_date, inputdata_root, cell_counts):
    """
    Get the text of the grid file, a ``config_grids.xml`` that CIME uses in
    place of E3SM's, with only what the pair of meshes needs

    Parameters
    ----------
    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    creation_date : str
        The creation date of the staged files, as ``YYYYMMDD``

    inputdata_root : str
        Where the case finds the staged files: ``$DIN_LOC_ROOT``, or a
        directory with the same layout

    cell_counts : dict of str to int
        The number of cells of the ``ocean`` and ``landice`` meshes

    Returns
    -------
    text : str
        The grid file
    """
    ocean = grids['ocean']
    landice = grids['landice']
    maps = dict(
        glc_to_ocn=names.map_path(landice, ocean, 'aave', creation_date),
        ocn_to_glc=names.map_path(ocean, landice, 'aave', creation_date),
    )
    for key, path in maps.items():
        maps[key] = _inputdata_path(path, inputdata_root, in_grid_file=True)
    template = Template(
        imp_res.files(__package__)
        .joinpath('config_grids.template')
        .read_text()
    )
    return template.render(
        model_grid=grids['model'],
        ocean_grid=ocean,
        landice_grid=landice,
        ocean_cells=cell_counts['ocean'],
        landice_cells=cell_counts['landice'],
        **maps,
    )


def get_shell_commands(
    experiment,
    grids,
    creation_date,
    inputdata_root,
    segments,
    couplings_per_day,
    ocean_dt,
    source_inputdata_root=None,
    job_wall_time=None,
):
    """
    Get the text of ``shell_commands``, which sets the case variables that
    name the staged files and give the time of the data-mode file's first
    record, turns off MALI's runoff to the ocean, turns on the coupler's
    budgets and sets the coupling intervals, the first segment's length,
    the restarts and the jobs

    Parameters
    ----------
    experiment : str
        The experiment

    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    creation_date : str
        The creation date of the staged files, as ``YYYYMMDD``

    inputdata_root : str
        Where the case finds the staged files: ``$DIN_LOC_ROOT``, or a
        directory with the same layout

    segments : list of Segment
        The segments the case runs in, one a job, from
        :py:func:`get_segments`

    couplings_per_day : dict of str to int
        The times a day the ``ocean`` and ``landice`` models couple

    ocean_dt : float
        The ocean's time step in seconds, which must divide its coupling
        interval

    source_inputdata_root : str, optional
        For an experiment that continues from another's restart, where the
        case finds the other experiment's staged initial conditions.  A
        branch run reads the restart in their place, but E3SM still names
        them.

    job_wall_time : str, optional
        The wall-clock time each job requests, as ``HH:MM:SS``, or None for
        the machine's default

    Returns
    -------
    text : str
        The shell commands
    """
    ocean = grids['ocean']
    landice = grids['landice']
    date = creation_date
    forcing = names.ocean_forcing_path(ocean, experiment, date)
    source = CONTINUES_FROM.get(experiment, experiment)
    if source != experiment and source_inputdata_root is None:
        raise ValueError(
            f'{experiment} continues from {source}, so it needs '
            f'source_inputdata_root.'
        )
    ic_files = {
        'MPASO_IC_FILE': names.ocean_initial_condition_path(
            ocean, source, date
        ),
        'MALI_IC_FILE': names.landice_initial_condition_path(
            landice, source, date
        ),
    }
    # each prefix ends just before the task count
    files = {
        'MPASO_DECOMP_FILE_PREFIX': (
            f'{inputdata.ocean_graph_path(ocean, date)}.part.'
        ),
        'MPASO_INTERIOR_RESTORING_FILE': forcing,
        'MPASO_TIDAL_MASK_FILE': forcing,
        'MALI_DECOMP_FILE_PREFIX': names.landice_partition_prefix(
            landice, date
        ),
        # MALI's geometry on the ocean, through the smoothed map, which is
        # not a map between a pair of grids in the grid file
        'GLC2OCN_SHELF_SMAPNAME': names.map_path(
            landice, ocean, 'smoothed', date
        ),
    }
    data_mode = get_mali_mode(experiment) == 'data'
    if data_mode:
        files['MALI_DATAMODE_FILE'] = names.landice_data_mode_path(
            landice, experiment, date
        )

    months = RUN_MONTHS[experiment]
    if sum(segment.months for segment in segments) != months:
        raise ValueError(
            f'The segments do not add up to the {months} months {experiment} '
            f'runs.'
        )
    resubmit = len(segments) - 1
    if job_wall_time is not None and not re.fullmatch(
        r'\d+:[0-5]\d:[0-5]\d', job_wall_time
    ):
        raise ValueError(
            f'The wall-clock time {job_wall_time} is not HH:MM:SS.'
        )

    ocean_ncpl = couplings_per_day['ocean']
    landice_ncpl = couplings_per_day['landice']
    if 86400 % ocean_ncpl != 0 or (86400 / ocean_ncpl) % ocean_dt != 0:
        raise ValueError(
            f'The ocean cannot couple {ocean_ncpl} times a day with a time '
            f'step of {ocean_dt} s.'
        )
    if ocean_ncpl % landice_ncpl != 0:
        raise ValueError(
            f'MALI cannot couple {landice_ncpl} times a day when the ocean '
            f'couples {ocean_ncpl} times.'
        )

    lines = [
        '#!/bin/bash',
        '',
        '# The staged files.  Single quotes keep $DIN_LOC_ROOT for CIME to',
        '# expand.',
    ]
    ic_root = inputdata_root if source == experiment else source_inputdata_root
    for variable, path in ic_files.items():
        path = _inputdata_path(path, ic_root)
        lines.append(f"./xmlchange '{variable}={path}'")
    for variable, path in files.items():
        path = _inputdata_path(path, inputdata_root)
        lines.append(f"./xmlchange '{variable}={path}'")
    if data_mode:
        xtimes, _ = get_monthly_record_times(year_count=1)
        lines.extend(
            [
                '',
                "# The time of the data-mode file's first record, from which",
                '# MALI counts the months between records',
                f"./xmlchange 'MALI_DATAMODE_REFERENCE_TIME={xtimes[0]}'",
            ]
        )
    if get_mali_mode(experiment) == 'prognostic':
        lines.extend(
            [
                '',
                "# The ocean's melt reaches MALI through ice-shelf",
                '# coupling, not thermal forcing, so the ocean sends MALI',
                "# no z-levels.  MALI's ISMIP6 melt, which would hold",
                '# them, is off.',
                './xmlchange GLC_NZOC=0',
            ]
        )
    lines.extend(
        [
            '',
            "# MALI's calving adds no water to the ocean",
            './xmlchange GLC_RUNOFF_TO_OCN=FALSE',
            '',
            "# The coupler's monthly and annual budgets, which include the",
            '# ice-shelf exchange',
            './xmlchange BUDGETS=TRUE',
            '',
            '# Couplings a day.  The stub atmosphere sets the base interval.',
            f'./xmlchange NCPL_BASE_PERIOD=day,ATM_NCPL={ocean_ncpl},'
            f'OCN_NCPL={ocean_ncpl},GLC_NCPL={landice_ncpl}',
            '',
            f'# {months} months in all, in {len(segments)} jobs, with',
            f'# restarts every {RESTART_MONTHS} months.  {NEXT_SEGMENT} sets '
            f'each',
            "# later job's months.",
            f'./xmlchange STOP_OPTION=nmonths,STOP_N={segments[0].months}',
            f'./xmlchange REST_OPTION=nmonths,REST_N={RESTART_MONTHS}',
            f'./xmlchange RESUBMIT={resubmit}',
            '',
        ]
    )
    if job_wall_time is not None:
        lines.extend(
            [
                '# The wall-clock time each job requests, for the longest',
                '# job',
                f'./xmlchange JOB_WALLCLOCK_TIME={job_wall_time} '
                f'--subgroup case.run',
                '',
            ]
        )
    return '\n'.join(lines)


def get_user_nl_mpaso(
    standalone,
    defaults,
    min_land_ice_fraction,
    ramp_land_ice_pressure=False,
):
    """
    Get the text of ``user_nl_mpaso``: the options the standalone run sets,
    less those E3SM sets itself, those E3SM would otherwise give a
    different value, whether each analysis member is on, and the options
    only an E3SM case has, which turn on the daily means, of
    :py:data:`DAILY_OCEAN_FIELDS` sampled every time step, the
    :py:data:`MONITORING_OPTIONS` and the :py:data:`OVERTURNING_OPTIONS`

    Parameters
    ----------
    standalone : dict
        The standalone run's namelist, as :py:func:`polaris.namelist.ingest`
        reads it

    defaults : dict
        MPAS-Ocean's default namelist, read the same way

    min_land_ice_fraction : float
        The land-ice fraction at or below which MPAS-Ocean's import of
        MALI's geometry leaves a cell open ocean

    ramp_land_ice_pressure : bool, optional
        Whether to ramp the land-ice pressure from MALI over each of MALI's
        coupling intervals, for a case in which MALI's geometry changes

    Returns
    -------
    text : str
        The namelist options
    """
    default_values = {
        option: value
        for group in defaults.values()
        for option, value in group.items()
    }
    standalone_options = {
        option for group in standalone.values() for option in group
    }
    missing = set(E3SM_DEFAULT_OPTIONS) - standalone_options
    if missing:
        raise ValueError(
            f'The standalone namelist lacks {", ".join(sorted(missing))}.'
        )

    e3sm_only = dict(E3SM_OCEAN_OPTIONS)
    e3sm_only[MIN_FRACTION_OPTION] = f'{min_land_ice_fraction:g}'
    e3sm_only[DAILY_SWITCH] = '.true.'
    e3sm_only[DAILY_COMPUTE_INTERVAL] = "'dt'"
    e3sm_only.update(MONITORING_OPTIONS)
    e3sm_only.update(OVERTURNING_OPTIONS)
    if ramp_land_ice_pressure:
        e3sm_only[RAMP_OPTION] = '.true.'

    lines = [
        "! The standalone MPAS-Ocean run's options, written by Polaris",
    ]
    analysis_members = dict()
    for group, options in standalone.items():
        if group.startswith('AM_'):
            switch = f'config_{group}_enable'
            if switch in options and switch not in e3sm_only:
                analysis_members[switch] = options[switch]
            continue
        if group in STANDALONE_GROUPS:
            selected = {
                option: value
                for option, value in options.items()
                if option in E3SM_DEFAULT_OPTIONS
            }
        else:
            selected = {
                option: value
                for option, value in options.items()
                if option not in E3SM_OWNED_OPTIONS
                and option not in e3sm_only
                and (
                    option in E3SM_DEFAULT_OPTIONS
                    or not _same(value, default_values.get(option))
                )
            }
        if not selected:
            continue
        lines.extend(['', f'! {group}'])
        for option, value in selected.items():
            lines.append(f'{option} = {value}')

    if analysis_members:
        lines.extend(
            ['', '! analysis members, on or off as in the standalone run']
        )
        for option, value in analysis_members.items():
            lines.append(f'{option} = {value}')

    lines.extend(['', '! E3SM only'])
    for option, value in e3sm_only.items():
        lines.append(f'{option} = {value}')
    lines.append('')
    return '\n'.join(lines)


def get_user_nl_mali(experiment, flow_param_a):
    """
    Get the text of ``user_nl_mali``.  A prognostic MALI also takes the
    MISMIP+ tasks' options and those of their Ice1r run, which IceOcean1r
    follows, except the melt under floating ice, which E3SM takes from the
    ocean.

    Parameters
    ----------
    experiment : str
        The experiment

    flow_param_a : float
        The MISMIP+ tasks' rate factor in Pa^-3 s^-1, from
        ``[mismip_plus] flow_param_a``

    Returns
    -------
    text : str
        The namelist options
    """
    lines = ['! MALI options, written by Polaris']
    for option, value in MALI_OPTIONS.items():
        lines.append(f'{option} = {value}')
    if get_mali_mode(experiment) == 'prognostic':
        lines.extend(
            ['', "! the MISMIP+ tasks' options, with those of their Ice1r run"]
        )
        options = {
            option: value
            for option, value in polaris.namelist.parse_replacements(
                'polaris.tasks.landice.mismip_plus', 'namelist.landice'
            ).items()
            if option not in MISMIP_PLUS_STANDALONE_OPTIONS
        }
        options['config_default_flowParamA'] = repr(flow_param_a)
        # Ice1r calves floating ice too thin to be dynamic, and icebergs,
        # and restores the calving front without preventing its retreat
        options['config_calving'] = "'thickness_threshold'"
        options['config_calving_thickness'] = repr(MALI_DYNAMIC_THICKNESS)
        options['config_remove_icebergs'] = '.true.'
        options['config_restore_calving_front'] = '.true.'
        options['config_restore_calving_front_prevent_retreat'] = '.false.'
        lines.extend(
            [f'{option} = {value}' for option, value in options.items()]
            + ['', "! MALI's defaults, where E3SM's differ"]
        )
        options = {
            option: value
            for option, value in MALI_E3SM_DEFAULT_OPTIONS.items()
            if option not in options
        }
        for option, value in options.items():
            lines.append(f'{option} = {value}')
    lines.append('')
    return '\n'.join(lines)


def get_readme(
    experiment, grids, layout_lines, time_integrator='RK4', segments=None
):
    """
    Get the text of the README beside the user-mods directory, with the
    compset a case is created with and the layout

    Parameters
    ----------
    experiment : str
        The experiment

    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    layout_lines : list of str
        The description of the layout

    time_integrator : str, optional
        The ocean's time integrator, one of :py:data:`TIME_INTEGRATORS`

    segments : list of Segment, optional
        The segments the case runs in, from :py:func:`get_segments`, which
        the README describes with ``next_segment.sh``

    Returns
    -------
    text : str
        The README
    """
    mode = get_mali_mode(experiment)
    compset = COMPSETS[mode]
    source = CONTINUES_FROM.get(experiment)
    branch_args = (
        []
        if source is None
        else [f'      -R <{source} case directory> -d <YYYY-MM-DD> \\']
    )
    lines = [
        f'The E3SM case configuration of MISOMIP {experiment} on '
        f'{grids["model"]}, with MALI',
        f"in {mode} mode and the ocean's {time_integrator} time integrator.",
        '',
        f'`{CREATE_CASE}` creates, sets up and builds a case, with the',
        "layout below.  It needs an E3SM checkout at FAnSSIE's",
        f'{E3SM_COMMIT} or later, on the machine the layout is for:',
        '',
        f'  ./{CREATE_CASE} -e <E3SM checkout> -c <case directory> \\',
        *branch_args,
        '      [-p <project>] [-C <compiler>] [-r <output root>] \\',
        '      [-o <ocean tasks>] [-g <MALI tasks>]',
        '',
        'Submit the case yourself.  To create a case by hand instead, use',
        'the MCT driver:',
        '',
        '  ./create_newcase --case <case> --driver mct \\',
        f'      --compset {compset} \\',
        f'      --res {grids["model"]} \\',
        '      --user-mods-dirs <this directory>/user_mods \\',
        '      --pesfile <this directory>/pes.xml',
        '',
        "`pes.xml` has the layout's tasks, with 1 thread a task, and its",
        'tasks per node.',
        '',
        'The layout:',
        '',
    ]
    lines.extend(f'  {line}' for line in layout_lines)
    if time_integrator == 'split_explicit':
        lines.extend(
            [
                '',
                'The split-explicit ocean also needs the per-layer limit on',
                f'drying of {SPLIT_EXPLICIT_PENDING}, which FAnSSIE does not',
                f'have yet.  It has no namelist option, so `{CREATE_CASE}`',
                'cannot check for it: without it, the ocean runs without the',
                'limit.  Build from an E3SM checkout that has it.',
            ]
        )
    lines.extend(
        [
            '',
            '`user_mods/` holds the grid file, `config_grids.xml`, which CIME',
            "uses in place of E3SM's, the standalone ocean run's options in",
            "`user_nl_mpaso`, MALI's in `user_nl_mali`, and `shell_commands`,",
            "which names the staged files, turns on the coupler's budgets and",
            'sets the coupling intervals and the run length.',
            '',
        ]
    )
    if mode == 'prognostic':
        lines.extend(
            [
                "MALI's Albany input is in `user_mods/SourceMods/src.mali/`.",
                '',
            ]
        )
    mali_streams = (
        " and MALI's monthly history and daily melt"
        if mode == 'prognostic'
        else ''
    )
    lines.extend(
        [
            f'`{CREATE_CASE}` runs `./preview_namelists`, then',
            f'`{EDIT_STREAMS}`, which copies the streams files E3SM wrote',
            "into the case's SourceMods with the ocean's daily melt means,",
            'daily maximum of the kinetic energy and hourly global',
            f'statistics{mali_streams} added.  A keepexe clone shares its',
            'SourceMods with the case it was cloned from, so replace the',
            'link with a copy before editing them.',
            '',
        ]
    )
    if segments is not None:
        lines.extend(_get_segment_lines(experiment, segments))
    if source is not None:
        lines.extend(
            [
                f"The case is a branch run from a {source} case's restarts",
                'on the date given with `-R` and `-d`.  The script copies the',
                "coupler's, the ocean's and MALI's restarts into the run",
                'directory and points `rpointer.drv` at the coupler restart.',
                '',
                f"Before creating it, check that the {source} case's ice on",
                'that date has no ice-free holes behind the calving front.',
                'MALI restores its calving front to the extent of the ice it',
                f'starts from, which a branch run takes from the {source}',
                'restart, so a hole there would stay ice-free and keep the',
                'ice from readvancing through it.',
                '',
            ]
        )
    return '\n'.join(lines)


def _get_segment_lines(experiment, segments):
    """
    Get the README's lines on the case's segments and ``next_segment.sh``
    """
    months = RUN_MONTHS[experiment]
    jobs: list[list[int]] = list()
    for segment in segments:
        if jobs and jobs[-1][1] == segment.months:
            jobs[-1][0] += 1
        else:
            jobs.append([1, segment.months])
    parts = [
        f'{length} months' if count == 1 else f'{count} of {length} months'
        for count, length in jobs
    ]
    if len(parts) == 1:
        described = parts[0]
    else:
        described = f'{", ".join(parts[:-1])} and {parts[-1]}'
    windows = get_daily_3d_windows(experiment)
    if windows == [(0, months)]:
        daily_3d = 'throughout'
    elif len(windows) == 1:
        daily_3d = f'in its first {DAILY_3D_MONTHS} months'
    else:
        daily_3d = f'in its first and last {DAILY_3D_MONTHS} months'
    fields = [f'`{name}`' for name in DAILY_3D_OCEAN_FIELDS]
    fields_text = f'{", ".join(fields[:-1])} and {fields[-1]}'
    job_count = '1 job' if len(segments) == 1 else f'{len(segments)} jobs'
    text = (
        f'The case runs {months} months in {job_count}: '
        f'{described}, with restarts every {RESTART_MONTHS} months.  The '
        f"ocean's daily means hold the 3D fields {fields_text} {daily_3d}.  "
        f'`{CREATE_CASE}` copies `{NEXT_SEGMENT}` into the case directory '
        f"and makes it CIME's `POSTRUN_SCRIPT`, which CIME runs after each "
        f'job, before it resubmits the case.  It reads the months run so '
        f"far from the coupler's restart pointer, `rpointer.drv`, and the "
        f"case's start, `RUN_STARTDATE`, or `RUN_REFDATE` for a branch run, "
        f"not from a count of jobs.  It sets the next job's `STOP_N` and "
        f'copies the streams file with or without the daily 3D fields from '
        f'`{OCEAN_STREAMS_DIR}/` into `SourceMods/src.mpaso/`.  It lowers '
        f'`RESUBMIT` to the jobs left, never raising it, and sets it to 0 '
        f'when the run is done.  It logs each change in '
        f'`next_segment.log` in the case directory, and it stops the chain, '
        f'exiting with an error, if it cannot tell the date, finds a date '
        f'that does not start a segment or cannot copy the file.  After its '
        f'own work, it runs `postrun.local` in the case directory, if there '
        f'is one, with the case directory as its argument.'
    )
    override = (
        'To stop the chain, set `RESUBMIT=0`.  To run on without the '
        'script changing anything, create `next_segment.skip` in the case '
        'directory; it still runs `postrun.local`.  To rerun a segment, '
        'resubmit as usual, since the script works from the date.'
    )
    return _wrap(text) + [''] + _wrap(override) + ['']


def _wrap(text):
    """
    Wrap a paragraph of the README
    """
    return textwrap.wrap(text, width=70)


def get_create_case_script(
    experiment, grids, task_counts, layout, machine, compiler
):
    """
    Get the text of the script that creates, sets up and builds a case.
    By default, every component runs on the layout's tasks.

    Parameters
    ----------
    experiment : str
        The experiment

    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    task_counts : dict of str to list of int
        The task counts the ``ocean`` and ``landice`` meshes are partitioned
        for

    layout : polaris.tasks.e3sm.init.misomip.layout.Layout
        The case's layout

    machine : str
        The machine the layout is for, or an empty string if Polaris has no
        name for it

    compiler : str
        The compiler Polaris was set up with, the case's by default

    Returns
    -------
    text : str
        The script
    """
    mode = get_mali_mode(experiment)
    template = Template(
        imp_res.files(__package__)
        .joinpath('create_case.template')
        .read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        experiment=experiment,
        source=CONTINUES_FROM.get(experiment),
        edit_streams=EDIT_STREAMS,
        next_segment=NEXT_SEGMENT,
        model_grid=grids['model'],
        mode=mode,
        compset=COMPSETS[mode],
        e3sm_commit=E3SM_COMMIT,
        machine=machine,
        compiler=compiler,
        tasks=layout.tasks,
        min_tasks=layout.bounds.min_tasks,
        max_tasks=layout.bounds.max_tasks,
        ocean_counts=' '.join(str(count) for count in task_counts['ocean']),
        landice_counts=' '.join(
            str(count) for count in task_counts['landice']
        ),
    )


def get_edit_streams_script(experiment):
    """
    Get the text of the script with which ``create_case.sh`` adds a case's
    output to the streams files E3SM writes.  With a prognostic MALI, the
    script also edits MALI's streams: its history takes the fields of the
    MISMIP+ tasks' output and :py:data:`MALI_HISTORY_FIELDS`.

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    text : str
        The script
    """
    mali_history_fields = get_mismip_plus_output_fields()
    for name in MALI_HISTORY_FIELDS:
        if name not in mali_history_fields:
            mali_history_fields.append(name)
    template = Template(
        imp_res.files(__package__)
        .joinpath('edit_streams.template')
        .read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        daily_ocean_fields=repr(DAILY_OCEAN_FIELDS),
        daily_3d_ocean_fields=repr(DAILY_3D_OCEAN_FIELDS),
        ocean_var_arrays=repr(OCEAN_VAR_ARRAYS),
        streams_dir=OCEAN_STREAMS_DIR,
        monthly_ocean_fields=repr(MONTHLY_OCEAN_FIELDS),
        snapshot_stream=SNAPSHOT_STREAM,
        snapshot_ocean_fields=repr(SNAPSHOT_OCEAN_FIELDS),
        snapshot_interval=SNAPSHOT_INTERVAL,
        daily_max_ocean_fields=repr(DAILY_MAX_OCEAN_FIELDS),
        global_stats_interval=GLOBAL_STATS_INTERVAL,
        daily_max_interval=DAILY_MAX_INTERVAL,
        mali_history_interval=MALI_HISTORY_INTERVAL,
        mali_history_fields=repr(mali_history_fields),
        mali_daily_fields=repr(MALI_DAILY_FIELDS),
        edit_landice=get_mali_mode(experiment) == 'prognostic',
    )


def get_next_segment_script(experiment, segments):
    """
    Get the text of the script that sets up each job of a case: its months,
    and the ocean's streams file with or without daily means of 3D fields

    Parameters
    ----------
    experiment : str
        The experiment

    segments : list of Segment
        The segments the case runs in, from :py:func:`get_segments`

    Returns
    -------
    text : str
        The script
    """
    template = Template(
        imp_res.files(__package__)
        .joinpath('next_segment.template')
        .read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        experiment=experiment,
        run_months=RUN_MONTHS[experiment],
        segment_count=len(segments),
        segment_starts=' '.join(str(segment.start) for segment in segments),
        segment_months=' '.join(str(segment.months) for segment in segments),
        segment_daily_3d=' '.join(
            str(int(segment.daily_3d)) for segment in segments
        ),
        streams_dir=OCEAN_STREAMS_DIR,
    )


def get_mismip_plus_output_fields():
    """
    Get the fields of the MISMIP+ tasks' MALI output stream

    Returns
    -------
    fields : list of str
        The fields, in the order of the streams file
    """
    text = (
        imp_res.files('polaris.tasks.landice.mismip_plus')
        .joinpath('streams.landice')
        .read_text()
    )
    match = re.search(r'<stream name="output".*?</stream>', text, re.DOTALL)
    if match is None:
        raise ValueError("The MISMIP+ tasks' streams have no output stream.")
    return re.findall(r'<var name="(\w+)"/>', match.group(0))


def get_pes_file(layout):
    """
    Get the text of the case's layout, a PE file that ``create_newcase``
    uses in place of the ocean's.  Every component runs on the layout's
    tasks, with 1 thread a task, and a node holds the layout's tasks per
    node.

    Parameters
    ----------
    layout : polaris.tasks.e3sm.init.misomip.layout.Layout
        The case's layout

    Returns
    -------
    text : str
        The PE file
    """
    template = Template(
        imp_res.files(__package__).joinpath('pes.template').read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        components=COMPONENTS,
        tasks=layout.tasks,
        tasks_per_node=layout.tasks_per_node,
    )


def _get_cell_counts():
    """
    Get the number of cells of each mesh from its SCRIP file
    """
    counts = dict()
    for grid in ['ocean', 'landice']:
        with open_dataset(f'{grid}_scrip.nc') as ds:
            counts[grid] = ds.sizes['grid_size']
    return counts


def _inputdata_path(path, inputdata_root, in_grid_file=False):
    """
    Get the path a case reads a staged file from.  A grid file names maps
    relative to ``$DIN_LOC_ROOT``.
    """
    prefix = 'inputdata/'
    if not path.startswith(prefix):
        raise ValueError(f'{path} is not in the staged inputdata tree.')
    relative = path[len(prefix) :]
    if in_grid_file and inputdata_root == DIN_LOC_ROOT:
        return relative
    return f'{inputdata_root}/{relative}'


def _same(value, default):
    """
    Whether a namelist value equals a default, which may be written
    differently, as ``1.0e-4`` and ``0.0001`` are
    """
    if default is None:
        return False
    return _normalize(value) == _normalize(default)


def _normalize(value):
    """
    A namelist value in a form that compares equal however it is written
    """
    value = value.strip().strip('\'"')
    lower = value.lower()
    if lower in ['.true.', 'true', 't']:
        return True
    if lower in ['.false.', 'false', 'f']:
        return False
    try:
        return float(lower.replace('d', 'e'))
    except ValueError:
        return value


def _write(filename, text, executable=False):
    """
    Write a text file
    """
    with open(filename, 'w') as handle:
        handle.write(text)
    if executable:
        os.chmod(filename, 0o755)
