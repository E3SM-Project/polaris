import importlib.resources as imp_res
import os

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

#: The section of config options for the case configuration
CASE_CONFIG_SECTION = 'misomip_case_config'

#: E3SM's inputdata directory, as a case variable that CIME expands
DIN_LOC_ROOT = '$DIN_LOC_ROOT'

#: The length of each experiment in months, as the protocols prescribe
RUN_MONTHS = {
    'ocean0': 12,
    'ocean1': 240,
    'ocean2': 240,
    'ocean3': 1200,
    'ocean4': 1200,
}

#: The earliest commit of FAnSSIE, E3SM's development branch for coupling the
#: ocean and ice sheets, that has every change the cases need
E3SM_COMMIT = 'eb0b74201c'

#: The compset of each mode of MALI, by long name
COMPSETS = {
    'static': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV',
    'data': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIADATA_SWAV',
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

#: What the step writes that is staged: the user-mods directory, and the
#: README, script and layout beside it
CASE_CONFIG_FILES = [USER_MODS, 'README', CREATE_CASE, PES]

#: The components of an MCT case, each with a task count in the layout
COMPONENTS = ['atm', 'lnd', 'rof', 'ice', 'ocn', 'glc', 'wav', 'cpl']

#: The config section of each mesh's graph partitions
PARTITION_SECTIONS = {
    'ocean': 'misomip_ocean_partitions',
    'landice': 'misomip_landice_partitions',
}


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
            the E3SM case shares

        ocean_config_filepath : str
            The config file of the experiment's ocean steps, relative to the
            base work directory, which says where MPAS-Ocean's default
            namelist is
        """
        if experiment not in RUN_MONTHS:
            raise ValueError(
                f'No E3SM case configuration for experiment {experiment}.'
            )
        super().__init__(
            component=component, name='case_config', subdir=subdir
        )
        self.experiment = experiment
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

    def run(self):
        """
        Write the user-mods directory, the README and the script
        """
        config = self.config
        experiment = self.experiment
        grids = names.get_grid_names(config)
        date = inputdata.get_creation_date(config, names.INPUTS_SECTION)
        section = config[CASE_CONFIG_SECTION]
        root = get_inputdata_root(config, experiment)
        months_per_job = section.getint('months_per_job')
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
                months_per_job,
                couplings_per_day,
                dt,
            ),
            executable=True,
        )
        _write(
            os.path.join(USER_MODS, 'user_nl_mpaso'),
            get_user_nl_mpaso(standalone, defaults),
        )
        _write(os.path.join(USER_MODS, 'user_nl_mali'), get_user_nl_mali())
        _write('README', get_readme(experiment, grids))
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
        _write(
            CREATE_CASE,
            get_create_case_script(experiment, grids, task_counts),
            executable=True,
        )
        _write(PES, get_pes_file(task_counts))


def get_mali_mode(experiment):
    """
    Get the mode MALI runs in for an experiment

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    mode : {'static', 'data'}
        The mode, a key of :py:data:`COMPSETS`
    """
    return 'data' if experiment in DATA_MODE_EXPERIMENTS else 'static'


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
    months_per_job,
    couplings_per_day,
    ocean_dt,
):
    """
    Get the text of ``shell_commands``, which sets the case variables that
    name the staged files, turns off MALI's runoff to the ocean, turns on
    the coupler's budgets and sets the coupling intervals and the run length

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

    months_per_job : int
        The months each job of the case runs

    couplings_per_day : dict of str to int
        The times a day the ``ocean`` and ``landice`` models couple

    ocean_dt : float
        The ocean's time step in seconds, which must divide its coupling
        interval

    Returns
    -------
    text : str
        The shell commands
    """
    ocean = grids['ocean']
    landice = grids['landice']
    date = creation_date
    forcing = names.ocean_forcing_path(ocean, experiment, date)
    # each prefix ends just before the task count
    files = {
        'MPASO_IC_FILE': names.ocean_initial_condition_path(
            ocean, experiment, date
        ),
        'MPASO_DECOMP_FILE_PREFIX': (
            f'{inputdata.ocean_graph_path(ocean, date)}.part.'
        ),
        'MPASO_INTERIOR_RESTORING_FILE': forcing,
        'MPASO_TIDAL_MASK_FILE': forcing,
        'MALI_IC_FILE': names.landice_initial_condition_path(
            landice, experiment, date
        ),
        'MALI_DECOMP_FILE_PREFIX': names.landice_partition_prefix(
            landice, date
        ),
    }
    if get_mali_mode(experiment) == 'data':
        files['MALI_DATAMODE_FILE'] = names.landice_data_mode_path(
            landice, experiment, date
        )

    months = RUN_MONTHS[experiment]
    if months % months_per_job != 0:
        raise ValueError(
            f'{experiment} runs {months} months, which is not a multiple of '
            f'months_per_job = {months_per_job}.'
        )
    resubmit = months // months_per_job - 1

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
    for variable, path in files.items():
        path = _inputdata_path(path, inputdata_root)
        lines.append(f"./xmlchange '{variable}={path}'")
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
            f'# {months} months in all, {months_per_job} per job',
            f'./xmlchange STOP_OPTION=nmonths,STOP_N={months_per_job}',
            f'./xmlchange REST_OPTION=nmonths,REST_N={months_per_job}',
            f'./xmlchange RESUBMIT={resubmit}',
            '',
        ]
    )
    return '\n'.join(lines)


def get_user_nl_mpaso(standalone, defaults):
    """
    Get the text of ``user_nl_mpaso``: the options the standalone run sets,
    less those E3SM sets itself, those E3SM would otherwise give a
    different value, and whether each analysis member is on

    Parameters
    ----------
    standalone : dict
        The standalone run's namelist, as :py:func:`polaris.namelist.ingest`
        reads it

    defaults : dict
        MPAS-Ocean's default namelist, read the same way

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

    lines = [
        "! The standalone MPAS-Ocean run's options, written by Polaris",
    ]
    analysis_members = dict()
    for group, options in standalone.items():
        if group.startswith('AM_'):
            switch = f'config_{group}_enable'
            if switch in options:
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
    for option, value in E3SM_OCEAN_OPTIONS.items():
        lines.append(f'{option} = {value}')
    lines.append('')
    return '\n'.join(lines)


def get_user_nl_mali():
    """
    Get the text of ``user_nl_mali``

    Returns
    -------
    text : str
        The namelist options
    """
    lines = ['! MALI options, written by Polaris']
    for option, value in MALI_OPTIONS.items():
        lines.append(f'{option} = {value}')
    lines.append('')
    return '\n'.join(lines)


def get_readme(experiment, grids):
    """
    Get the text of the README beside the user-mods directory, with the
    compset a case is created with

    Parameters
    ----------
    experiment : str
        The experiment

    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    Returns
    -------
    text : str
        The README
    """
    mode = get_mali_mode(experiment)
    compset = COMPSETS[mode]
    lines = [
        f'The E3SM case configuration of MISOMIP {experiment} on '
        f'{grids["model"]}, with MALI',
        f'in {mode} mode.',
        '',
        f'`{CREATE_CASE}` creates, sets up and builds a case, with a layout',
        "whose tasks match the meshes' partitions.  It needs an E3SM",
        f"checkout at FAnSSIE's {E3SM_COMMIT} or later:",
        '',
        f'  ./{CREATE_CASE} -e <E3SM checkout> -c <case directory> \\',
        '      [-m <machine>] [-p <project>] [-C <compiler>] \\',
        '      [-r <output root>] [-o <ocean tasks>] [-g <MALI tasks>]',
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
        'and set NTASKS_OCN and NTASKS_GLC to counts the meshes are',
        'partitioned for.  `pes.xml` gives every task 1 thread, so the',
        "machine's own MPI tasks per node apply.",
        '',
        '`user_mods/` holds the grid file, `config_grids.xml`, which CIME',
        "uses in place of E3SM's, the standalone ocean run's options in",
        "`user_nl_mpaso`, MALI's in `user_nl_mali`, and `shell_commands`,",
        "which names the staged files, turns on the coupler's budgets and",
        'sets the coupling intervals and the run length.',
        '',
    ]
    return '\n'.join(lines)


def get_create_case_script(experiment, grids, task_counts):
    """
    Get the text of the script that creates, sets up and builds a case.
    By default, the ocean and MALI each run on the most tasks both meshes
    are partitioned for.

    Parameters
    ----------
    experiment : str
        The experiment

    grids : dict of str to str
        E3SM's names of the ``ocean``, ``landice`` and ``model`` grids

    task_counts : dict of str to list of int
        The task counts the ``ocean`` and ``landice`` meshes are partitioned
        for

    Returns
    -------
    text : str
        The script
    """
    tasks = _get_default_tasks(task_counts)
    mode = get_mali_mode(experiment)
    template = Template(
        imp_res.files(__package__)
        .joinpath('create_case.template')
        .read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        experiment=experiment,
        model_grid=grids['model'],
        mode=mode,
        compset=COMPSETS[mode],
        e3sm_commit=E3SM_COMMIT,
        ocean_tasks=tasks,
        landice_tasks=tasks,
        ocean_counts=' '.join(str(count) for count in task_counts['ocean']),
        landice_counts=' '.join(
            str(count) for count in task_counts['landice']
        ),
    )


def get_pes_file(task_counts):
    """
    Get the text of the case's layout, a PE file that ``create_newcase``
    uses in place of the ocean's.  Every task has 1 thread, so the machine's
    own tasks per node apply.  By default, the ocean and MALI each run on
    the most tasks both meshes are partitioned for, and the other
    components on the ocean's tasks.

    Parameters
    ----------
    task_counts : dict of str to list of int
        The task counts the ``ocean`` and ``landice`` meshes are partitioned
        for

    Returns
    -------
    text : str
        The PE file
    """
    tasks = _get_default_tasks(task_counts)
    template = Template(
        imp_res.files(__package__).joinpath('pes.template').read_text(),
        keep_trailing_newline=True,
    )
    return template.render(
        components=COMPONENTS, ocean_tasks=tasks, landice_tasks=tasks
    )


def _get_default_tasks(task_counts):
    """
    The most tasks both meshes are partitioned for
    """
    shared = set(task_counts['ocean']) & set(task_counts['landice'])
    if not shared:
        raise ValueError(
            'The ocean and MALI meshes are partitioned for no task count in '
            'common.'
        )
    return max(shared)


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
