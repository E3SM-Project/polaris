import os
import re
import subprocess
import xml.etree.ElementTree as ET
from glob import glob

import pytest

import polaris.namelist
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.misomip import get_misomip_experiment_steps
from polaris.tasks.e3sm.init.misomip.case_config import (
    COMPONENTS,
    COMPSETS,
    DAILY_OCEAN_FIELDS,
    DAILY_SWITCH,
    DIN_LOC_ROOT,
    E3SM_COMMIT,
    E3SM_DEFAULT_OPTIONS,
    E3SM_OWNED_OPTIONS,
    MALI_DAILY_FIELDS,
    MALI_HISTORY_FIELDS,
    MALI_HISTORY_INTERVAL,
    MISMIP_PLUS_STANDALONE_OPTIONS,
    MONTHLY_OCEAN_FIELDS,
    RUN_MONTHS,
    get_case_config_files,
    get_create_case_script,
    get_edit_streams_script,
    get_grid_file,
    get_inputdata_root,
    get_mali_mode,
    get_mismip_plus_output_fields,
    get_pes_file,
    get_readme,
    get_shell_commands,
    get_user_nl_mali,
    get_user_nl_mpaso,
)
from polaris.tasks.e3sm.init.misomip.layout import Layout, TaskBounds
from polaris.tasks.landice import landice
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'misomip-o4km-li1km'
GRIDS = {
    'ocean': 'misomip-o4km',
    'landice': 'misomip-li1km',
    'model': 'misomip-o4km-li1km',
}
DATE = '20250101'
COUPLINGS = {'ocean': 48, 'landice': 1}
DT = 24.0

MPAS_OCEAN = os.path.join(
    os.path.dirname(__file__),
    '..',
    '..',
    '..',
    '..',
    'e3sm_submodules',
    'FAnSSIE',
    'components',
    'mpas-ocean',
)

#: Options with differing defaults that E3SM sets for itself
E3SM_MANAGED = {
    'config_block_decomp_file_prefix',
    'config_calendar_type',
    'config_restart_timestamp_name',
    'config_write_output_on_startup',
}


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean, landice]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()


def _namelists():
    defaults = {
        'time_management': {'config_run_duration': "'0010_00:00:00'"},
        'time_integration': {
            'config_dt': "'00:05:00'",
            'config_time_integrator': "'split_explicit_ab2'",
        },
        'hmix': {'config_hmix_scaleWithMesh': '.false.'},
        'cvmix': {
            'config_cvmix_background_viscosity': '1.0e-4',
            'config_use_cvmix_kpp': '.false.',
        },
        'AM_globalStats': {'config_AM_globalStats_enable': '.false.'},
        'AM_mixedLayerDepths': {'config_AM_mixedLayerDepths_enable': '.true.'},
    }
    standalone = {
        'time_management': {'config_run_duration': "'0031_00:00:00'"},
        'time_integration': {
            'config_dt': "'0000_00:00:24'",
            'config_time_integrator': "'RK4'",
        },
        'hmix': {'config_hmix_scaleWithMesh': '.false.'},
        'cvmix': {
            'config_cvmix_background_viscosity': '0.0001',
            'config_use_cvmix_kpp': '.true.',
        },
        'AM_globalStats': {
            'config_AM_globalStats_enable': '.true.',
            'config_AM_globalStats_compute_interval': "'output_interval'",
        },
        'AM_mixedLayerDepths': {
            'config_AM_mixedLayerDepths_enable': '.false.',
        },
        'forcing': {'config_use_bulk_wind_stress': '.true.'},
    }
    for option in E3SM_DEFAULT_OPTIONS:
        if not any(option in group for group in standalone.values()):
            standalone.setdefault('other', {})[option] = '.false.'
    return standalone, defaults


def _options(text):
    options = dict()
    for line in text.splitlines():
        if '=' in line and not line.startswith('!'):
            option, value = line.split('=')
            options[option.strip()] = value.strip()
    return options


def test_user_nl_mpaso_has_the_standalone_options():
    standalone, defaults = _namelists()
    options = _options(get_user_nl_mpaso(standalone, defaults, 1e-3))
    # set by the standalone run
    assert options['config_time_integrator'] == "'RK4'"
    assert options['config_use_cvmix_kpp'] == '.true.'
    # E3SM's default differs, so written even where the standalone run takes
    # MPAS-Ocean's
    assert options['config_dt'] == "'0000_00:00:24'"
    assert options['config_hmix_scaleWithMesh'] == '.false.'
    for option in E3SM_DEFAULT_OPTIONS:
        assert option in options
    # MPAS-Ocean's default, written another way
    assert 'config_cvmix_background_viscosity' not in options
    # analysis members on and off as in the standalone run, whatever the
    # defaults, with their output left to E3SM
    assert options['config_AM_globalStats_enable'] == '.true.'
    assert options['config_AM_mixedLayerDepths_enable'] == '.false.'
    assert 'config_AM_globalStats_compute_interval' not in options
    # left to E3SM
    assert 'config_run_duration' not in options
    assert 'config_use_bulk_wind_stress' not in options
    assert options['config_glc_ice_shelf_coupling_import_geometry'] == (
        '.true.'
    )
    # the import's open-ocean threshold, as the initial conditions have it
    assert options['config_glc_ice_shelf_coupling_min_floating_fraction'] == (
        '0.001'
    )


def test_user_nl_mpaso_needs_every_e3sm_default_option():
    standalone, defaults = _namelists()
    standalone['other'].pop('config_include_KE_vertex')
    with pytest.raises(ValueError, match='config_include_KE_vertex'):
        get_user_nl_mpaso(standalone, defaults, 1e-3)


def _registry_defaults():
    defaults = dict()
    pattern = re.compile(
        r'<nml_option\s+name="(\w+)"[^>]*?default_value="([^"]*)"', re.S
    )
    filenames = glob(
        os.path.join(MPAS_OCEAN, 'src', '**', 'Registry*.xml'), recursive=True
    )
    for filename in filenames:
        with open(filename) as handle:
            for option, value in pattern.findall(handle.read()):
                defaults[option] = value
    return defaults


@pytest.mark.skipif(
    not os.path.exists(os.path.join(MPAS_OCEAN, 'bld')),
    reason="E3SM's MPAS-Ocean is not checked out",
)
def test_e3sm_default_options_are_those_that_differ():
    """
    Every option whose E3SM default differs from MPAS-Ocean's, or that E3SM
    gives a default only for some grids, is written with the standalone
    run's value.  Fails when E3SM's defaults change.
    """
    from polaris.tasks.e3sm.init.misomip.case_config import _same

    registry = {
        option.lower(): value for option, value in _registry_defaults().items()
    }
    filename = os.path.join(
        MPAS_OCEAN, 'bld', 'namelist_files', 'namelist_defaults_mpaso.xml'
    )
    generic = dict()
    by_grid = set()
    for element in ET.parse(filename).getroot():
        if element.attrib:
            by_grid.add(element.tag)
        else:
            generic[element.tag] = element.text or ''

    expected = set()
    for option in by_grid - set(generic):
        expected.add(option)
    for option, value in generic.items():
        default = registry.get(option.lower())
        if default is not None and not _same(value, default):
            expected.add(option)
    managed = {
        option.lower() for option in E3SM_MANAGED | set(E3SM_OWNED_OPTIONS)
    }
    # analysis members' switches are written from their groups
    expected = {
        option.lower()
        for option in expected
        if option.lower() in registry
        and not option.lower().startswith('config_am_')
        and option.lower() not in managed
    }

    written = {option.lower() for option in E3SM_DEFAULT_OPTIONS}
    assert expected - written == set()


def test_shell_commands_name_the_staged_files():
    text = get_shell_commands(
        'ocean3', GRIDS, DATE, DIN_LOC_ROOT, 12, COUPLINGS, DT
    )
    ocn = '$DIN_LOC_ROOT/ocn/mpas-o/misomip-o4km'
    glc = '$DIN_LOC_ROOT/glc/mpasli/misomip-li1km'
    lines = text.splitlines()
    for line in [
        f"./xmlchange 'MPASO_IC_FILE={ocn}/"
        f"mpaso.misomip-o4km.ocean3.{DATE}.nc'",
        f"./xmlchange 'MPASO_DECOMP_FILE_PREFIX={ocn}/partitions/"
        f"mpas-o.graph.info.{DATE}.part.'",
        f"./xmlchange 'MPASO_INTERIOR_RESTORING_FILE={ocn}/"
        f"mpaso.misomip-o4km.ocean3_forcing.{DATE}.nc'",
        f"./xmlchange 'MPASO_TIDAL_MASK_FILE={ocn}/"
        f"mpaso.misomip-o4km.ocean3_forcing.{DATE}.nc'",
        f"./xmlchange 'MALI_IC_FILE={glc}/misomip-li1km.ocean3.{DATE}.nc'",
        f"./xmlchange 'MALI_DECOMP_FILE_PREFIX={glc}/"
        f"mpasli.graph.info.{DATE}.part.'",
        f"./xmlchange 'MALI_DATAMODE_FILE={glc}/"
        f"misomip-li1km.ocean3_datamode.{DATE}.nc'",
        "./xmlchange 'MALI_DATAMODE_REFERENCE_TIME=0001-01-01_00:00:00'",
        './xmlchange GLC_RUNOFF_TO_OCN=FALSE',
        './xmlchange BUDGETS=TRUE',
        './xmlchange NCPL_BASE_PERIOD=day,ATM_NCPL=48,OCN_NCPL=48,GLC_NCPL=1',
        './xmlchange STOP_OPTION=nmonths,STOP_N=12',
        './xmlchange RESUBMIT=99',
    ]:
        assert line in lines


def test_shell_commands_static_mali_has_no_data_mode_file():
    text = get_shell_commands(
        'ocean0', GRIDS, DATE, '/short/inputdata', 1, COUPLINGS, DT
    )
    assert 'MALI_DATAMODE_FILE' not in text
    assert 'MALI_DATAMODE_REFERENCE_TIME' not in text
    assert (
        f"./xmlchange 'MPASO_IC_FILE=/short/inputdata/ocn/mpas-o/"
        f"misomip-o4km/mpaso.misomip-o4km.ocean0.{DATE}.nc'"
    ) in text.splitlines()
    assert './xmlchange RESUBMIT=11' in text.splitlines()


@pytest.mark.parametrize('experiment', list(RUN_MONTHS))
def test_shell_commands_data_mode_file_has_reference_time(experiment):
    # MALI's buildnml stops if a case names a data-mode file without the
    # time of its first record
    text = get_shell_commands(
        experiment,
        GRIDS,
        DATE,
        DIN_LOC_ROOT,
        12,
        COUPLINGS,
        DT,
        source_inputdata_root=DIN_LOC_ROOT,
    )
    has_file = 'MALI_DATAMODE_FILE=' in text
    assert has_file == (get_mali_mode(experiment) == 'data')
    assert has_file == ('MALI_DATAMODE_REFERENCE_TIME=' in text)


def test_shell_commands_need_whole_jobs():
    with pytest.raises(ValueError, match='multiple'):
        get_shell_commands(
            'ocean0', GRIDS, DATE, DIN_LOC_ROOT, 5, COUPLINGS, DT
        )


@pytest.mark.parametrize(
    'couplings, dt, match',
    [
        ({'ocean': 48, 'landice': 1}, 28.0, 'ocean cannot couple'),
        ({'ocean': 7, 'landice': 1}, 24.0, 'ocean cannot couple'),
        ({'ocean': 48, 'landice': 5}, 24.0, 'MALI cannot couple'),
    ],
)
def test_shell_commands_need_whole_coupling_intervals(couplings, dt, match):
    with pytest.raises(ValueError, match=match):
        get_shell_commands(
            'ocean0', GRIDS, DATE, DIN_LOC_ROOT, 1, couplings, dt
        )


COUNTS = {'ocean': [2, 4, 8, 48, 64, 66], 'landice': [3, 4, 8, 48, 64, 600]}

LAYOUT = Layout(
    bounds=TaskBounds(target=28, min_tasks=2, max_tasks=68),
    tasks_per_node=64,
    batch=True,
    nodes=1,
    tasks=64,
)


def test_create_case_script():
    text = get_create_case_script(
        'ocean3', GRIDS, COUNTS, LAYOUT, 'chrysalis', 'gnu'
    )
    lines = text.splitlines()
    assert lines[0] == '#!/bin/bash'
    # the layout's tasks, the fewest and most, and the partitions
    assert 'ocean_tasks=64' in lines
    assert 'landice_tasks=64' in lines
    assert 'min_tasks=2' in lines
    assert 'max_tasks=68' in lines
    assert 'ocean_counts="2 4 8 48 64 66"' in lines
    assert 'landice_counts="3 4 8 48 64 600"' in lines
    # Polaris's machine and compiler
    assert 'machine=chrysalis' in lines
    assert 'compiler=gnu' in lines
    assert 'while getopts "e:c:p:C:r:o:g:h" option; do' in lines
    assert (
        '      --compset '
        '2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIADATA_SWAV'
    ) in lines
    assert '      --res misomip-o4km-li1km' in lines
    assert f'merge-base --is-ancestor {E3SM_COMMIT} HEAD' in text
    # the layout beside the script, in place of MPAS-Ocean's
    assert '      --pesfile "$here/pes.xml"' in lines
    # submitting is left to the person
    assert not any(line.strip().startswith('./case.submit') for line in lines)
    result = subprocess.run(
        ['bash', '-n'], input=text, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr


def test_create_case_script_without_a_machine():
    text = get_create_case_script('ocean0', GRIDS, COUNTS, LAYOUT, '', 'gnu')
    assert 'machine=' in text.splitlines()


@pytest.mark.parametrize(
    'option, tasks, message',
    [
        ('-o', 1, '1 tasks for the ocean lie outside the 2 to 68'),
        ('-o', 72, '72 tasks for the ocean lie outside the 2 to 68'),
        ('-g', 66, "No partition of MALI's mesh is for 66 tasks"),
    ],
)
def test_create_case_script_checks_the_tasks(tmp_path, option, tasks, message):
    """
    The script stops on a task count outside the bounds or with no
    partition, before it looks at the E3SM checkout
    """
    script = tmp_path / 'create_case.sh'
    script.write_text(
        get_create_case_script('ocean0', GRIDS, COUNTS, LAYOUT, '', 'gnu')
    )
    result = subprocess.run(
        [
            'bash',
            str(script),
            '-e',
            str(tmp_path / 'e3sm'),
            '-c',
            str(tmp_path / 'case'),
            option,
            str(tasks),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert not (tmp_path / 'case').exists()


def test_pes_file():
    root = ET.fromstring(get_pes_file(LAYOUT))
    # only the catch-all entry, which no machine-specific one overrides
    assert [grid.attrib['name'] for grid in root.iter('grid')] == ['any']
    assert [mach.attrib['name'] for mach in root.iter('mach')] == ['any']
    pes = root.find('grid/mach/pes')
    assert pes is not None
    assert pes.attrib == {'compset': 'any', 'pesize': 'any'}
    for component in COMPONENTS:
        assert pes.findtext(f'ntasks/ntasks_{component}') == '64'
        assert pes.findtext(f'nthrds/nthrds_{component}') == '1'
        assert pes.findtext(f'rootpe/rootpe_{component}') == '0'
    # Polaris's tasks per node, so CIME's nodes match Polaris's
    assert pes.findtext('MAX_MPITASKS_PER_NODE') == '64'
    assert pes.find('MAX_TASKS_PER_NODE') is None


def test_readme_gives_the_layout():
    lines = ['the ocean: a goal of 100 cells per task', 'layout: 64 tasks']
    text = get_readme('ocean0', GRIDS, lines)
    for line in lines:
        assert f'  {line}' in text.splitlines()
    assert '[-m <machine>]' not in text
    assert '--pesfile <this directory>/pes.xml' in text


@pytest.mark.parametrize(
    'value, expected',
    [
        ('', DIN_LOC_ROOT),
        ('/short/inputdata', '/short/inputdata'),
        ('/short/{experiment}/inputdata', '/short/ocean3/inputdata'),
    ],
)
def test_inputdata_root_names_the_experiment(value, expected):
    from polaris.config import PolarisConfigParser

    config = PolarisConfigParser()
    config.add_section('misomip_case_config')
    config.set('misomip_case_config', 'inputdata_root', value)
    assert get_inputdata_root(config, 'ocean3') == expected


def test_grid_file():
    counts = {'ocean': 2759, 'landice': 62035}
    text = get_grid_file(GRIDS, DATE, DIN_LOC_ROOT, counts)
    root = ET.fromstring(text)
    model_grid = root.find('grids/model_grid')
    assert model_grid is not None
    assert model_grid.attrib['alias'] == 'misomip-o4km-li1km'
    domains = {
        domain.attrib['name']: domain.findtext('nx')
        for domain in root.iter('domain')
    }
    assert domains == {
        'null': '0',
        'misomip-o4km': '2759',
        'misomip-li1km': '62035',
    }
    maps = {item.attrib['name']: item.text for item in root.iter('map')}
    glc_to_ocn = (
        f'cpl/gridmaps/misomip-li1km/'
        f'map_misomip-li1km_to_misomip-o4km_aave.{DATE}.nc'
    )
    glc_to_ocn_smoothed = (
        f'cpl/gridmaps/misomip-li1km/'
        f'map_misomip-li1km_to_misomip-o4km_smoothed.{DATE}.nc'
    )
    ocn_to_glc = (
        f'cpl/gridmaps/misomip-o4km/'
        f'map_misomip-o4km_to_misomip-li1km_aave.{DATE}.nc'
    )
    assert maps == {
        'OCN2GLC_SHELF_FMAPNAME': ocn_to_glc,
        'OCN2GLC_SHELF_SMAPNAME': ocn_to_glc,
        'GLC2OCN_FMAPNAME': glc_to_ocn,
        'GLC2OCN_SMAPNAME': glc_to_ocn_smoothed,
    }

    text = get_grid_file(GRIDS, DATE, '/short/inputdata', counts)
    maps = {
        item.attrib['name']: item.text
        for item in ET.fromstring(text).iter('map')
    }
    assert maps['GLC2OCN_FMAPNAME'] == f'/short/inputdata/{glc_to_ocn}'


@pytest.mark.parametrize(
    'experiment, namelist_experiment',
    [
        ('ocean0', 'ocean0'),
        ('ocean3', 'ocean3'),
        ('iceocean1r', 'iceocean1r'),
        # IceOcean1ra continues from IceOcean1r and shares its namelist
        ('iceocean1ra', 'iceocean1r'),
    ],
)
def test_every_experiment_has_a_case_config(experiment, namelist_experiment):
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, experiment)
    step = steps['case_config']
    assert step.path == (
        f'e3sm/init/{MESH_NAME}/misomip/{experiment}/case_config'
    )
    targets = {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    }
    assert targets['namelist.ocean'] == (
        f'ocean/planar/misomip/{MESH_NAME}/{namelist_experiment}/forward/'
        f'namelist.ocean'
    )
    assert targets['ocean.cfg'] == (
        f'ocean/planar/misomip/{MESH_NAME}/{experiment}/misomip_ocean.cfg'
    )
    assert 'case_config' in steps['assemble'].product_steps


@pytest.mark.parametrize(
    'experiment, mode',
    [
        ('ocean0', 'static'),
        ('ocean3', 'data'),
        ('iceocean1r', 'prognostic'),
        ('iceocean1ra', 'prognostic'),
    ],
)
def test_mali_mode(experiment, mode):
    assert get_mali_mode(experiment) == mode
    # the streams script is staged only where MALI is prognostic
    assert ('edit_streams.py' in get_case_config_files(experiment)) == (
        mode == 'prognostic'
    )


def test_prognostic_compset_uses_albany():
    # MALI's shallow-ice compsets build MALI without Albany
    assert '_MALI%SIA' in COMPSETS['static']
    assert '_MALI%SIA' in COMPSETS['data']
    assert '_MALI_' in COMPSETS['prognostic']


def test_shell_commands_branch_run_names_the_source_initial_conditions():
    text = get_shell_commands(
        'iceocean1ra',
        GRIDS,
        DATE,
        '/short/iceocean1ra',
        12,
        COUPLINGS,
        DT,
        source_inputdata_root='/short/iceocean1r',
    )
    lines = text.splitlines()
    assert (
        f"./xmlchange 'MPASO_IC_FILE=/short/iceocean1r/ocn/mpas-o/"
        f"misomip-o4km/mpaso.misomip-o4km.iceocean1r.{DATE}.nc'"
    ) in lines
    assert (
        f"./xmlchange 'MALI_IC_FILE=/short/iceocean1r/glc/mpasli/"
        f"misomip-li1km/misomip-li1km.iceocean1r.{DATE}.nc'"
    ) in lines
    # its own restoring
    assert (
        f"./xmlchange 'MPASO_INTERIOR_RESTORING_FILE=/short/iceocean1ra/ocn/"
        f'mpas-o/misomip-o4km/mpaso.misomip-o4km.iceocean1ra_forcing.'
        f"{DATE}.nc'"
    ) in lines
    with pytest.raises(ValueError, match='source_inputdata_root'):
        get_shell_commands(
            'iceocean1ra', GRIDS, DATE, DIN_LOC_ROOT, 12, COUPLINGS, DT
        )


def test_user_nl_mpaso_turns_on_the_daily_means_once():
    standalone, defaults = _namelists()
    standalone['AM_timeSeriesStatsDaily'] = {DAILY_SWITCH: '.false.'}
    text = get_user_nl_mpaso(standalone, defaults, 1e-3, daily_means=True)
    switches = [
        line for line in text.splitlines() if line.startswith(DAILY_SWITCH)
    ]
    assert switches == [f'{DAILY_SWITCH} = .true.']
    text = get_user_nl_mpaso(standalone, defaults, 1e-3)
    assert _options(text)[DAILY_SWITCH] == '.false.'


def test_user_nl_mali_prognostic_takes_the_mismip_plus_options():
    mismip_plus = polaris.namelist.parse_replacements(
        'polaris.tasks.landice.mismip_plus', 'namelist.landice'
    )
    text = get_user_nl_mali('iceocean1r', 6.0e-25)
    options = _options(text)
    # each option once, since E3SM's namelist builder rejects repeats
    lines = [line for line in text.splitlines() if '=' in line]
    assert len(lines) == len(options)
    # Ice1r's calving in place of the MISMIP+ tasks' default
    ice1r = {'config_calving', 'config_remove_icebergs'}
    for option, value in mismip_plus.items():
        if option in MISMIP_PLUS_STANDALONE_OPTIONS:
            assert option not in options
        elif option not in ice1r:
            assert options[option] == value
    assert options['config_default_flowParamA'] == '6e-25'
    assert options['config_calving'] == "'thickness_threshold'"
    assert options['config_remove_icebergs'] == '.true.'
    assert options['config_always_compute_fem_grid'] == '.false.'
    # E3SM takes the melt from the ocean
    assert 'config_basal_mass_bal_float' not in options

    options = _options(get_user_nl_mali('ocean3', 6.0e-25))
    assert 'config_calving' not in options
    assert 'config_default_flowParamA' not in options


def _write_streams(rundir):
    ocean = """<streams>
<stream name="timeSeriesStatsDailyOutput" type="output"
        filename_template="case.mpaso.hist.am.timeSeriesStatsDaily.nc">
    <var name="normalVelocity"/>
</stream>
<stream name="timeSeriesStatsMonthlyOutput" type="output"
        filename_template="case.mpaso.hist.am.timeSeriesStatsMonthly.nc">
    <var name="landIceFreshwaterFlux"/>
</stream>
</streams>
"""
    landice = """<streams>
<stream name="output" type="output" io_type="pnetcdf"
        filename_template="case.mali.hist.$Y-$M-$D_$S.nc"
        output_interval="0000-00-10_00:00:00">
    <var name="thickness"/>
</stream>
</streams>
"""
    (rundir / 'streams.ocean').write_text(ocean)
    (rundir / 'streams.landice').write_text(landice)


def _vars(stream):
    return [var.attrib['name'] for var in stream.iter('var')]


def _write_registries(srcroot, missing):
    fields = {
        'mpas-ocean': ['xtime'] + DAILY_OCEAN_FIELDS + MONTHLY_OCEAN_FIELDS,
        'mpas-albany-landice': (
            ['xtime']
            + get_mismip_plus_output_fields()
            + MALI_HISTORY_FIELDS
            + MALI_DAILY_FIELDS
        ),
    }
    for component, names in fields.items():
        src = srcroot / 'components' / component / 'src'
        src.mkdir(parents=True)
        lines = [
            f'<var name="{name}" type="real" dimensions="nCells Time"/>'
            for name in names
            if name != missing
        ]
        (src / 'Registry.xml').write_text('\n'.join(lines))


def _run_edit_streams(tmp_path, missing_field=None, missing_stream=None):
    """
    Run the script in a fake case whose xmlquery gives the run directory,
    with E3SM's streams files, and the source root, with Registry files
    """
    case_dir = tmp_path / 'case'
    rundir = tmp_path / 'run'
    srcroot = tmp_path / 'e3sm'
    case_dir.mkdir()
    rundir.mkdir()
    _write_streams(rundir)
    if missing_stream is not None:
        filename, stream = missing_stream
        path = rundir / filename
        path.write_text(
            path.read_text().replace(f'name="{stream}"', 'name="other"')
        )
    _write_registries(srcroot, missing_field)
    xmlquery = case_dir / 'xmlquery'
    xmlquery.write_text(
        '#!/bin/bash\n'
        'case $2 in\n'
        f'    RUNDIR) echo {rundir} ;;\n'
        f'    SRCROOT) echo {srcroot} ;;\n'
        'esac\n'
    )
    xmlquery.chmod(0o755)
    script = tmp_path / 'edit_streams.py'
    script.write_text(get_edit_streams_script())
    result = subprocess.run(
        ['python3', str(script)], cwd=case_dir, text=True, capture_output=True
    )
    return case_dir, result


@pytest.mark.parametrize(
    'missing',
    ['landIceFreshwaterFluxNotSentToGlc', 'floatingBasalMassBalApplied'],
)
def test_edit_streams_script_stops_without_a_registry_field(tmp_path, missing):
    case_dir, result = _run_edit_streams(tmp_path, missing_field=missing)
    assert result.returncode != 0
    assert f'{missing} not defined' in result.stderr
    assert not (case_dir / 'SourceMods').exists()


@pytest.mark.parametrize(
    'missing',
    [
        ('streams.ocean', 'timeSeriesStatsDailyOutput'),
        ('streams.ocean', 'timeSeriesStatsMonthlyOutput'),
        ('streams.landice', 'output'),
    ],
)
def test_edit_streams_script_stops_without_a_stream(tmp_path, missing):
    case_dir, result = _run_edit_streams(tmp_path, missing_stream=missing)
    assert result.returncode != 0
    assert f'No stream {missing[1]}' in result.stderr
    # neither file is written
    assert not (case_dir / 'SourceMods').exists()


def test_edit_streams_script(tmp_path):
    case_dir, result = _run_edit_streams(tmp_path)
    assert result.returncode == 0, result.stderr

    ocean = ET.parse(case_dir / 'SourceMods/src.mpaso/streams.ocean')
    streams = {s.attrib['name']: s for s in ocean.getroot()}
    # E3SM's daily list is replaced
    assert _vars(streams['timeSeriesStatsDailyOutput']) == (
        ['xtime'] + DAILY_OCEAN_FIELDS
    )
    assert _vars(streams['timeSeriesStatsMonthlyOutput']) == (
        ['landIceFreshwaterFlux'] + MONTHLY_OCEAN_FIELDS
    )

    landice = ET.parse(case_dir / 'SourceMods/src.mali/streams.landice')
    streams = {s.attrib['name']: s for s in landice.getroot()}
    output = streams['output']
    assert output.attrib['output_interval'] == MALI_HISTORY_INTERVAL
    history = _vars(output)
    for name in get_mismip_plus_output_fields() + MALI_HISTORY_FIELDS:
        assert history.count(name) == 1
    daily = streams['dailyOutput']
    assert _vars(daily) == ['xtime'] + MALI_DAILY_FIELDS
    assert daily.attrib['filename_template'] == (
        'case.mali.hist.daily.$Y-$M-$D_$S.nc'
    )
    assert daily.attrib['io_type'] == 'pnetcdf'


def test_edit_streams_script_refuses_a_shared_source_mods(tmp_path):
    case_dir = tmp_path / 'case'
    case_dir.mkdir()
    (tmp_path / 'base_source_mods').mkdir()
    os.symlink(tmp_path / 'base_source_mods', case_dir / 'SourceMods')
    script = tmp_path / 'edit_streams.py'
    script.write_text(get_edit_streams_script())
    result = subprocess.run(
        ['python3', str(script)], cwd=case_dir, text=True, capture_output=True
    )
    assert result.returncode != 0
    assert 'keepexe' in result.stderr


def test_create_case_script_branches_iceocean1ra():
    text = get_create_case_script(
        'iceocean1ra', GRIDS, COUNTS, LAYOUT, 'chrysalis', 'gnu'
    )
    lines = text.splitlines()
    assert 'while getopts "e:c:R:d:p:C:r:o:g:h" option; do' in lines
    assert ('./xmlchange "RUN_TYPE=branch,RUN_REFCASE=$source_case"') in lines
    assert 'echo "${restarts[0]}" > "$run_dir/rpointer.drv"' in lines
    # the streams are edited after the restarts are in place, before the
    # build
    assert lines.index('./preview_namelists') > lines.index(
        'echo "${restarts[0]}" > "$run_dir/rpointer.drv"'
    )
    assert lines.index('./case.build') > lines.index(
        'python3 "$here/edit_streams.py"'
    )
    result = subprocess.run(
        ['bash', '-n'], input=text, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr

    # IceOcean1r has the streams edit but no branch
    text = get_create_case_script(
        'iceocean1r', GRIDS, COUNTS, LAYOUT, 'chrysalis', 'gnu'
    )
    assert './preview_namelists' in text.splitlines()
    assert 'RUN_TYPE=branch' not in text
    # the other experiments have neither
    text = get_create_case_script(
        'ocean3', GRIDS, COUNTS, LAYOUT, 'chrysalis', 'gnu'
    )
    assert './preview_namelists' not in text.splitlines()
    assert 'RUN_TYPE=branch' not in text


def test_create_case_script_needs_the_iceocean1r_restart(tmp_path):
    script = tmp_path / 'create_case.sh'
    script.write_text(
        get_create_case_script('iceocean1ra', GRIDS, COUNTS, LAYOUT, '', 'gnu')
    )
    result = subprocess.run(
        ['bash', str(script), '-e', 'e3sm', '-c', str(tmp_path / 'case')],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert 'usage' in result.stderr


def test_readme_describes_the_branch_run():
    text = get_readme('iceocean1ra', GRIDS, ['layout: 64 tasks'])
    assert '-R <iceocean1r case directory> -d <YYYY-MM-DD>' in text
    assert 'branch run' in text
    assert 'edit_streams.py' in text
    text = get_readme('ocean0', GRIDS, ['layout: 64 tasks'])
    assert 'branch run' not in text
    assert 'edit_streams.py' not in text
