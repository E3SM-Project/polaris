import importlib.resources as imp_res
import os

from jinja2 import Template
from mpas_tools.io import open_dataset

import polaris.namelist
from polaris.config import PolarisConfigParser
from polaris.e3sm.init import inputdata
from polaris.landice.mismip_plus.geometry import ICE_DENSITY, OCEAN_DENSITY
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

#: The compset of each mode of MALI, by long name
COMPSETS = {
    'static': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV',
    'data': '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIADATA_SWAV',
}

#: MPAS-Ocean namelist groups whose options a standalone run sets but an
#: E3SM case leaves to E3SM: the run's times, I/O, partitions, the
#: standalone land-ice forcing, which the coupler replaces, and analysis
#: members, whose output E3SM configures
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
    'config_AM_mocStreamfunction_enable',
    # E3SM's defaults differ
    'config_bulk_wind_stress_interp_isotropic',
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
    'config_use_bulk_wind_stress',
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

#: What the step writes that is staged: the user-mods directory and the
#: README beside it
CASE_CONFIG_FILES = [USER_MODS, 'README']


class CaseConfigStep(Step):
    """
    A step for writing the E3SM case configuration of one MISOMIP
    experiment: a user-mods directory, with the grid file, and a README with
    the compset

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

    def run(self):
        """
        Write the user-mods directory and the README
        """
        config = self.config
        experiment = self.experiment
        grids = names.get_grid_names(config)
        date = inputdata.get_creation_date(config, names.INPUTS_SECTION)
        section = config[CASE_CONFIG_SECTION]
        root = inputdata.get_nonempty_option(
            config, CASE_CONFIG_SECTION, 'inputdata_root'
        )
        if root is None:
            root = DIN_LOC_ROOT
        months_per_job = section.getint('months_per_job')

        os.makedirs(USER_MODS, exist_ok=True)
        _write(
            os.path.join(USER_MODS, 'config_grids.xml'),
            get_grid_file(grids, date, root, _get_cell_counts()),
        )
        filename = os.path.join(USER_MODS, 'shell_commands')
        _write(
            filename,
            get_shell_commands(experiment, grids, date, root, months_per_job),
        )
        os.chmod(filename, 0o755)
        ocean_config = PolarisConfigParser()
        ocean_config.add_from_file('ocean.cfg')
        defaults = polaris.namelist.ingest(
            ocean_config.get('namelists', 'forward')
        )
        standalone = polaris.namelist.ingest('namelist.ocean')
        _write(
            os.path.join(USER_MODS, 'user_nl_mpaso'),
            get_user_nl_mpaso(standalone, defaults),
        )
        _write(os.path.join(USER_MODS, 'user_nl_mali'), get_user_nl_mali())
        _write('README', get_readme(experiment, grids))


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
    experiment, grids, creation_date, inputdata_root, months_per_job
):
    """
    Get the text of ``shell_commands``, which sets the case variables that
    name the staged files, turns off MALI's runoff to the ocean and sets the
    run length

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
    less those E3SM sets itself, and those E3SM would otherwise give a
    different value

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
    for group, options in standalone.items():
        if group in STANDALONE_GROUPS or group.startswith('AM_'):
            selected = {
                option: value
                for option, value in options.items()
                if option in E3SM_DEFAULT_OPTIONS
            }
        else:
            selected = {
                option: value
                for option, value in options.items()
                if option in E3SM_DEFAULT_OPTIONS
                or not _same(value, default_values.get(option))
            }
        if not selected:
            continue
        lines.extend(['', f'! {group}'])
        for option, value in selected.items():
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
        'Create a case from it with the MCT driver:',
        '',
        '  ./create_newcase --case <case> --driver mct \\',
        f'      --compset {compset} \\',
        f'      --res {grids["model"]} \\',
        '      --user-mods-dirs <this directory>/user_mods',
        '',
        '`user_mods/` holds the grid file, `config_grids.xml`, which CIME',
        "uses in place of E3SM's, the standalone ocean run's options in",
        "`user_nl_mpaso`, MALI's in `user_nl_mali`, and `shell_commands`,",
        'which names the staged files and sets the run length.',
        '',
    ]
    return '\n'.join(lines)


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


def _write(filename, text):
    """
    Write a text file
    """
    with open(filename, 'w') as handle:
        handle.write(text)
