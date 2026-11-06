import os
import re
import subprocess
import xml.etree.ElementTree as ET
from glob import glob

import pytest

import polaris.namelist
from polaris.component import Component
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.misomip import (
    MisomipTask,
    get_misomip_experiment_steps,
)
from polaris.tasks.e3sm.init.misomip.case_config import (
    COMPONENTS,
    COMPSETS,
    DAILY_3D_OCEAN_FIELDS,
    DAILY_COMPUTE_INTERVAL,
    DAILY_MAX_INTERVAL,
    DAILY_MAX_OCEAN_FIELDS,
    DAILY_OCEAN_FIELDS,
    DAILY_SWITCH,
    DIN_LOC_ROOT,
    E3SM_COMMIT,
    E3SM_DEFAULT_OPTIONS,
    E3SM_OWNED_OPTIONS,
    GLOBAL_STATS_INTERVAL,
    MALI_DAILY_FIELDS,
    MALI_E3SM_DEFAULT_OPTIONS,
    MALI_E3SM_OWNED_OPTIONS,
    MALI_HISTORY_FIELDS,
    MALI_HISTORY_INTERVAL,
    MISMIP_PLUS_STANDALONE_OPTIONS,
    MONITORING_OPTIONS,
    MONTHLY_OCEAN_FIELDS,
    RAMP_OPTION,
    RUN_MONTHS,
    SPLIT_EXPLICIT_PENDING,
    CaseConfigStep,
    check_time_integrator,
    get_case_config_files,
    get_create_case_script,
    get_edit_streams_script,
    get_grid_file,
    get_inputdata_root,
    get_mali_mode,
    get_mismip_plus_output_fields,
    get_next_segment_script,
    get_pes_file,
    get_readme,
    get_segments,
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

MALI = os.path.join(os.path.dirname(MPAS_OCEAN), 'mpas-albany-landice')

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


def _registry_defaults(component=MPAS_OCEAN):
    defaults = dict()
    pattern = re.compile(
        r'<nml_option\s+name="(\w+)"[^>]*?default_value="([^"]*)"', re.S
    )
    filenames = glob(
        os.path.join(component, 'src', '**', 'Registry*.xml'), recursive=True
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
        'ocean3',
        GRIDS,
        DATE,
        DIN_LOC_ROOT,
        get_segments('ocean3', 48),
        COUPLINGS,
        DT,
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
        f"./xmlchange 'GLC2OCN_SHELF_SMAPNAME=$DIN_LOC_ROOT/cpl/gridmaps/"
        f'misomip-li1km/map_misomip-li1km_to_misomip-o4km_smoothed.'
        f"{DATE}.nc'",
        "./xmlchange 'MALI_DATAMODE_REFERENCE_TIME=0001-01-01_00:00:00'",
        './xmlchange GLC_RUNOFF_TO_OCN=FALSE',
        './xmlchange BUDGETS=TRUE',
        './xmlchange NCPL_BASE_PERIOD=day,ATM_NCPL=48,OCN_NCPL=48,GLC_NCPL=1',
        # the first year's job, restarts every year and 27 jobs
        './xmlchange STOP_OPTION=nmonths,STOP_N=12',
        './xmlchange REST_OPTION=nmonths,REST_N=12',
        './xmlchange RESUBMIT=26',
    ]:
        assert line in lines


def test_shell_commands_static_mali_has_no_data_mode_file():
    text = get_shell_commands(
        'ocean0',
        GRIDS,
        DATE,
        '/short/inputdata',
        get_segments('ocean0', 12),
        COUPLINGS,
        DT,
    )
    assert 'MALI_DATAMODE_FILE' not in text
    assert 'MALI_DATAMODE_REFERENCE_TIME' not in text
    assert (
        f"./xmlchange 'MPASO_IC_FILE=/short/inputdata/ocn/mpas-o/"
        f"misomip-o4km/mpaso.misomip-o4km.ocean0.{DATE}.nc'"
    ) in text.splitlines()
    assert './xmlchange RESUBMIT=0' in text.splitlines()


@pytest.mark.parametrize('experiment', list(RUN_MONTHS))
def test_shell_commands_data_mode_file_has_reference_time(experiment):
    # MALI's buildnml stops if a case names a data-mode file without the
    # time of its first record
    text = get_shell_commands(
        experiment,
        GRIDS,
        DATE,
        DIN_LOC_ROOT,
        get_segments(experiment, 12),
        COUPLINGS,
        DT,
        source_inputdata_root=DIN_LOC_ROOT,
    )
    has_file = 'MALI_DATAMODE_FILE=' in text
    assert has_file == (get_mali_mode(experiment) == 'data')
    assert has_file == ('MALI_DATAMODE_REFERENCE_TIME=' in text)
    # a prognostic MALI gets no ocean thermal forcing, whose z-levels it
    # would have nowhere to put
    assert ('./xmlchange GLC_NZOC=0' in text.splitlines()) == (
        get_mali_mode(experiment) == 'prognostic'
    )


def test_shell_commands_set_the_wall_time():
    def commands(job_wall_time=None):
        return get_shell_commands(
            'ocean3',
            GRIDS,
            DATE,
            DIN_LOC_ROOT,
            get_segments('ocean3', 48),
            COUPLINGS,
            DT,
            job_wall_time=job_wall_time,
        )

    text = commands('30:00:00')
    assert (
        './xmlchange JOB_WALLCLOCK_TIME=30:00:00 --subgroup case.run'
    ) in text.splitlines()
    assert 'JOB_WALLCLOCK_TIME' not in commands()
    with pytest.raises(ValueError, match='HH:MM:SS'):
        commands('30h')


def test_shell_commands_need_the_whole_run():
    with pytest.raises(ValueError, match='do not add up'):
        get_shell_commands(
            'ocean1',
            GRIDS,
            DATE,
            DIN_LOC_ROOT,
            get_segments('ocean1', 12)[:-1],
            COUPLINGS,
            DT,
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
            'ocean0',
            GRIDS,
            DATE,
            DIN_LOC_ROOT,
            get_segments('ocean0', 12),
            couplings,
            dt,
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


def test_readme_names_the_split_explicit_change_fanssie_lacks():
    lines = ['layout: 64 tasks']
    assert SPLIT_EXPLICIT_PENDING not in get_readme('ocean0', GRIDS, lines)
    text = get_readme('iceocean1r', GRIDS, lines, 'split_explicit')
    assert "the ocean's split_explicit time integrator" in text
    assert SPLIT_EXPLICIT_PENDING in text


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
    ocn_to_glc = (
        f'cpl/gridmaps/misomip-o4km/'
        f'map_misomip-o4km_to_misomip-li1km_aave.{DATE}.nc'
    )
    assert maps == {
        'OCN2GLC_SHELF_FMAPNAME': ocn_to_glc,
        'OCN2GLC_SHELF_SMAPNAME': ocn_to_glc,
        'GLC2OCN_FMAPNAME': glc_to_ocn,
        'GLC2OCN_SMAPNAME': glc_to_ocn,
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
@pytest.mark.parametrize(
    'integrator, subdir', [('RK4', ''), ('split_explicit', 'split_explicit/')]
)
def test_every_experiment_has_a_case_config(
    experiment, namelist_experiment, integrator, subdir
):
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, experiment)
    step = steps[f'{subdir}case_config']
    assert step.time_integrator == integrator
    assert step.path == (
        f'e3sm/init/{MESH_NAME}/misomip/{experiment}/{subdir}case_config'
    )
    targets = {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    }
    # each integrator's case takes its own standalone run's namelist and
    # config
    ocean_dir = f'ocean/planar/misomip/{MESH_NAME}/{namelist_experiment}'
    assert targets['namelist.ocean'] == (
        f'{ocean_dir}/{subdir}forward/namelist.ocean'
    )
    assert targets['ocean.cfg'] == f'{ocean_dir}/{subdir}misomip_ocean.cfg'
    assert f'{subdir}case_config' in steps['assemble'].product_steps


@pytest.mark.parametrize('experiment', ['ocean3', 'iceocean1r', 'iceocean1ra'])
def test_task_steps_have_unique_names(experiment):
    # a task keys its steps by name, so the two forward runs and the two
    # case configurations need their own
    _reset_shared_components()
    task = MisomipTask(
        component=Component(name='e3sm/init'),
        mesh_name=MESH_NAME,
        experiment=experiment,
    )
    assert task.steps['case_config'].time_integrator == 'RK4'
    split = task.steps['split_explicit_case_config']
    assert split.time_integrator == 'split_explicit'
    assert split.subdir.endswith('split_explicit/case_config')
    forward = 'split_explicit_forward'
    assert task.steps[forward].subdir.endswith('split_explicit/forward')


def test_split_explicit_forward_shares_the_initial_condition():
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, 'iceocean1r')
    rk4 = steps['ocean/forward']
    split = steps['ocean/split_explicit/forward']
    section = 'isomip_plus_forward'
    assert rk4.config.get(section, 'time_integrator') == 'RK4'
    assert split.config.get(section, 'time_integrator') == 'split_explicit'
    # the SSH adjustment, which both runs start from, keeps RK4
    ssh_steps = [
        step for name, step in steps.items() if 'ssh_adjustment' in name
    ]
    assert ssh_steps
    for step in ssh_steps:
        assert step.config.get('ssh_adjustment', 'time_integrator') == 'RK4'
    rk4_inputs = {entry['filename']: entry for entry in rk4.input_data}
    split_inputs = {entry['filename']: entry for entry in split.input_data}
    for filename, entry in rk4_inputs.items():
        if entry['work_dir_target'] is not None:
            assert (
                split_inputs[filename]['work_dir_target']
                == (entry['work_dir_target'])
            )


def _split_explicit_namelist():
    return {
        'time_integration': {
            'config_dt': "'0000_00:02:00'",
            'config_time_integrator': "'split_explicit'",
        },
        'split_explicit_ts': {'config_split_pv_coriolis': '.true.'},
    }


def test_check_time_integrator_accepts_the_options():
    check_time_integrator(_split_explicit_namelist(), 'split_explicit')
    rk4 = {'time_integration': {'config_time_integrator': "'RK4'"}}
    check_time_integrator(rk4, 'RK4')


def test_check_time_integrator_needs_the_integrator():
    with pytest.raises(ValueError, match='time integrator split_explicit'):
        check_time_integrator(_split_explicit_namelist(), 'RK4')


def test_check_time_integrator_needs_the_yaml_options():
    # a build older than an option drops it from the rendered namelist
    standalone = _split_explicit_namelist()
    standalone['split_explicit_ts'].pop('config_split_pv_coriolis')
    with pytest.raises(ValueError, match='config_split_pv_coriolis'):
        check_time_integrator(standalone, 'split_explicit')


def test_case_config_needs_a_known_time_integrator():
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, 'ocean0')
    step = steps['case_config']
    with pytest.raises(ValueError, match='time integrator'):
        CaseConfigStep(
            component=step.component,
            subdir='other',
            experiment='ocean0',
            mesh_steps={
                'ocean': steps['ocean_mesh'],
                'landice': steps['landice_mesh'],
            },
            forward_step=steps['ocean/forward'],
            ocean_config_filepath='misomip_ocean.cfg',
            time_integrator='RK3',
        )


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
    # every experiment has the streams script
    assert 'edit_streams.py' in get_case_config_files(experiment)


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
        get_segments('iceocean1ra', 48),
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
            'iceocean1ra',
            GRIDS,
            DATE,
            DIN_LOC_ROOT,
            get_segments('iceocean1ra', 48),
            COUPLINGS,
            DT,
        )


def test_user_nl_mpaso_ramps_the_land_ice_pressure():
    standalone, defaults = _namelists()
    text = get_user_nl_mpaso(
        standalone, defaults, 1e-3, ramp_land_ice_pressure=True
    )
    assert _options(text)[RAMP_OPTION] == '.true.'
    # E3SM sets the interval of the ramp from the case's coupling
    assert 'config_glc_ice_shelf_coupling_interval' not in _options(text)
    text = get_user_nl_mpaso(standalone, defaults, 1e-3)
    assert RAMP_OPTION not in _options(text)


def test_user_nl_mpaso_turns_on_the_daily_means_once():
    standalone, defaults = _namelists()
    custom = 'config_AM_timeSeriesStatsCustom_enable'
    standalone['AM_timeSeriesStatsDaily'] = {DAILY_SWITCH: '.false.'}
    standalone['AM_timeSeriesStatsCustom'] = {custom: '.false.'}
    text = get_user_nl_mpaso(standalone, defaults, 1e-3)
    for switch in [DAILY_SWITCH, custom]:
        switches = [
            line for line in text.splitlines() if line.startswith(switch)
        ]
        assert switches == [f'{switch} = .true.']
    # every time step, not E3SM's hourly samples
    assert _options(text)[DAILY_COMPUTE_INTERVAL] == "'dt'"
    # the daily maximum, checked every time step
    for option, value in MONITORING_OPTIONS.items():
        assert _options(text)[option] == value


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
    ice1r = {
        'config_calving',
        'config_remove_icebergs',
        'config_restore_calving_front',
    }
    for option, value in mismip_plus.items():
        if option in MISMIP_PLUS_STANDALONE_OPTIONS:
            assert option not in options
        elif option not in ice1r:
            assert options[option] == value
    assert options['config_default_flowParamA'] == '6e-25'
    assert options['config_calving'] == "'thickness_threshold'"
    assert options['config_remove_icebergs'] == '.true.'
    assert options['config_restore_calving_front'] == '.true.'
    assert options['config_restore_calving_front_prevent_retreat'] == (
        '.false.'
    )
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
<stream name="timeSeriesStatsCustomOutput" type="output"
        filename_template="case.mpaso.hist.am.timeSeriesStatsCustom.nc"
        output_interval="00-01-00_00:00:00">
</stream>
<stream name="globalStatsOutput" type="output"
        filename_template="case.mpaso.hist.am.globalStats.nc"
        output_interval="00-00-01_00:00:00">
    <var_struct name="globalStatsAM"/>
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
    return [
        var.attrib['name'] for var in stream if var.tag in ['var', 'var_array']
    ]


def _write_registries(srcroot, missing):
    fields = {
        'mpas-ocean': (
            ['xtime']
            + DAILY_OCEAN_FIELDS
            + DAILY_3D_OCEAN_FIELDS
            + MONTHLY_OCEAN_FIELDS
            + DAILY_MAX_OCEAN_FIELDS
        ),
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
        # activeTracers is a variable array, as in E3SM's Registry
        lines = [
            f'<{"var_array" if name == "activeTracers" else "var"} '
            f'name="{name}" type="real" dimensions="nCells Time"/>'
            for name in names
            if name != missing
        ]
        (src / 'Registry.xml').write_text('\n'.join(lines))


def _run_edit_streams(
    tmp_path, missing_field=None, missing_stream=None, experiment='iceocean1r'
):
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
    script.write_text(get_edit_streams_script(experiment))
    result = subprocess.run(
        ['python3', str(script)], cwd=case_dir, text=True, capture_output=True
    )
    return case_dir, result


@pytest.mark.parametrize(
    'missing',
    [
        'landIceFreshwaterFluxNotSentToGlc',
        'kineticEnergyCell',
        'activeTracers',
        'floatingBasalMassBalApplied',
    ],
)
def test_edit_streams_script_stops_without_a_registry_field(tmp_path, missing):
    case_dir, result = _run_edit_streams(tmp_path, missing_field=missing)
    assert result.returncode != 0
    assert f'{missing} not defined' in result.stderr
    assert not (case_dir / 'SourceMods').exists()
    assert not (case_dir / 'ocean_streams').exists()


@pytest.mark.parametrize(
    'missing',
    [
        ('streams.ocean', 'timeSeriesStatsDailyOutput'),
        ('streams.ocean', 'timeSeriesStatsMonthlyOutput'),
        ('streams.ocean', 'timeSeriesStatsCustomOutput'),
        ('streams.ocean', 'globalStatsOutput'),
        ('streams.landice', 'output'),
    ],
)
def test_edit_streams_script_stops_without_a_stream(tmp_path, missing):
    case_dir, result = _run_edit_streams(tmp_path, missing_stream=missing)
    assert result.returncode != 0
    assert f'No stream {missing[1]}' in result.stderr
    # no file is written
    assert not (case_dir / 'SourceMods').exists()
    assert not (case_dir / 'ocean_streams').exists()


def test_edit_streams_script(tmp_path):
    case_dir, result = _run_edit_streams(tmp_path)
    assert result.returncode == 0, result.stderr

    # next_segment.sh copies one of the ocean's files into SourceMods
    assert not (case_dir / 'SourceMods/src.mpaso').exists()
    for daily_3d in [False, True]:
        variant = 'with' if daily_3d else 'without'
        ocean = ET.parse(
            case_dir / f'ocean_streams/streams.ocean.{variant}_daily_3d'
        )
        streams = {s.attrib['name']: s for s in ocean.getroot()}
        # E3SM's daily list is replaced
        daily = streams['timeSeriesStatsDailyOutput']
        expected = ['xtime'] + DAILY_OCEAN_FIELDS
        if daily_3d:
            expected += DAILY_3D_OCEAN_FIELDS
        assert _vars(daily) == expected
        tags = {var.attrib['name']: var.tag for var in daily}
        assert tags.get('activeTracers', 'var_array') == 'var_array'
        assert _vars(streams['timeSeriesStatsMonthlyOutput']) == (
            ['landIceFreshwaterFlux'] + MONTHLY_OCEAN_FIELDS
        )
        # the daily maxima, and hourly global statistics
        custom = streams['timeSeriesStatsCustomOutput']
        assert _vars(custom) == ['xtime'] + DAILY_MAX_OCEAN_FIELDS
        assert custom.attrib['output_interval'] == DAILY_MAX_INTERVAL
        global_stats = streams['globalStatsOutput']
        assert global_stats.attrib['output_interval'] == GLOBAL_STATS_INTERVAL
        assert [child.tag for child in global_stats] == ['var_struct']

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


def test_edit_streams_script_leaves_a_static_mali(tmp_path):
    # Ocean0-4 get the ocean's output, and MALI keeps E3SM's streams, so
    # MALI's Registry is not read
    case_dir, result = _run_edit_streams(
        tmp_path,
        missing_field='floatingBasalMassBalApplied',
        experiment='ocean3',
    )
    assert result.returncode == 0, result.stderr
    ocean = ET.parse(case_dir / 'ocean_streams/streams.ocean.without_daily_3d')
    streams = {s.attrib['name']: s for s in ocean.getroot()}
    assert _vars(streams['timeSeriesStatsDailyOutput']) == (
        ['xtime'] + DAILY_OCEAN_FIELDS
    )
    assert not (case_dir / 'SourceMods').exists()


def test_edit_streams_script_refuses_a_shared_source_mods(tmp_path):
    case_dir = tmp_path / 'case'
    case_dir.mkdir()
    (tmp_path / 'base_source_mods').mkdir()
    os.symlink(tmp_path / 'base_source_mods', case_dir / 'SourceMods')
    script = tmp_path / 'edit_streams.py'
    script.write_text(get_edit_streams_script('iceocean1r'))
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
    # the other experiments have the streams edit but no branch
    text = get_create_case_script(
        'ocean3', GRIDS, COUNTS, LAYOUT, 'chrysalis', 'gnu'
    )
    lines = text.splitlines()
    assert './preview_namelists' in lines
    assert 'RUN_TYPE=branch' not in text
    # the first job is set up from the edited streams, before the build,
    # and CIME sets up each later one
    start = '"./next_segment.sh" "$PWD" --start'
    assert lines.index(start) > lines.index('python3 "$here/edit_streams.py"')
    assert lines.index('./case.build') > lines.index(
        './xmlchange "POSTRUN_SCRIPT=$PWD/next_segment.sh"'
    )


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
    # the extent MALI restores comes from IceOcean1r's ice
    assert 'no ice-free holes behind the calving front' in ' '.join(
        text.split()
    )
    assert 'branch run' in text
    assert 'edit_streams.py' in text
    text = get_readme('ocean0', GRIDS, ['layout: 64 tasks'])
    assert 'branch run' not in text
    assert 'edit_streams.py' in text
    assert "MALI's monthly history" not in text


@pytest.mark.skipif(
    not os.path.exists(os.path.join(MALI, 'bld')),
    reason="E3SM's MALI is not checked out",
)
def test_mali_e3sm_default_options_are_those_that_differ():
    """
    Every MALI option whose E3SM default differs from MALI's own, which the
    MISMIP+ tasks run with, is written for a prognostic MALI or kept as
    E3SM's for a stated reason.  Fails when E3SM's defaults change.
    """
    from polaris.tasks.e3sm.init.misomip.case_config import _same

    registry = {
        option.lower(): value
        for option, value in _registry_defaults(MALI).items()
    }
    filename = os.path.join(
        MALI, 'bld', 'namelist_files', 'namelist_defaults_mali.xml'
    )
    differ = set()
    for element in ET.parse(filename).getroot():
        option = element.tag.lower()
        default = registry.get(option)
        if element.attrib or default is None:
            continue
        if not _same(element.text or '', default):
            differ.add(option)

    written = set(_options(get_user_nl_mali('iceocean1r', 6.0e-25)))
    kept = set(MALI_E3SM_OWNED_OPTIONS)
    # subglacial hydrology is off in both, so its options are unused
    assert not _same(registry['config_sgh'], '.true.')
    unused = {option for option in differ if option.startswith('config_sgh_')}
    accounted = {option.lower() for option in written | kept} | unused
    assert differ - accounted == set()

    # MALI's own defaults, and only where E3SM's differ
    for option, value in MALI_E3SM_DEFAULT_OPTIONS.items():
        assert option.lower() in differ
        assert _same(value, registry[option.lower()])


@pytest.mark.parametrize(
    'experiment, months_per_job, months, daily_3d',
    [
        ('ocean0', 12, [12], [True]),
        ('ocean1', 12, [12] * 20, [True] + [False] * 19),
        (
            'iceocean1r',
            48,
            [12] + [48] * 24 + [24, 12],
            [True] + [False] * 25 + [True],
        ),
    ],
)
def test_segments(experiment, months_per_job, months, daily_3d):
    segments = get_segments(experiment, months_per_job)
    assert [segment.months for segment in segments] == months
    assert [segment.daily_3d for segment in segments] == daily_3d
    starts = [segment.start for segment in segments]
    assert starts == [sum(months[:index]) for index in range(len(months))]
    assert sum(months) == RUN_MONTHS[experiment]


@pytest.mark.parametrize('months_per_job', [0, 5, 18])
def test_segments_need_whole_years(months_per_job):
    with pytest.raises(ValueError, match='multiple'):
        get_segments('ocean3', months_per_job)


def _fake_case(tmp_path, experiment='iceocean1r', **values):
    """
    A case directory whose xmlquery and xmlchange read and write files, with
    the ocean's streams files and next_segment.sh
    """
    case_dir = tmp_path / 'case'
    rundir = tmp_path / 'run'
    xml = case_dir / 'xml'
    for path in [xml, rundir, case_dir / 'ocean_streams']:
        path.mkdir(parents=True)
    defaults = dict(
        RUN_TYPE='startup',
        RUN_STARTDATE='0001-01-01',
        RUN_REFDATE='0001-01-01',
        RUNDIR=str(rundir),
        RESUBMIT='26',
        STOP_OPTION='nmonths',
        STOP_N='12',
    )
    defaults.update(values)
    for variable, value in defaults.items():
        (xml / variable).write_text(value)
    (case_dir / 'xmlquery').write_text(
        '#!/bin/bash\ncat "$(dirname "$0")/xml/$2"\n'
    )
    (case_dir / 'xmlchange').write_text(
        '#!/bin/bash\n'
        'IFS== read -r variable value <<< "$1"\n'
        'echo "$1" >> "$(dirname "$0")/changes"\n'
        'printf %s "$value" > "$(dirname "$0")/xml/$variable"\n'
    )
    for variant in ['with', 'without']:
        (
            case_dir / f'ocean_streams/streams.ocean.{variant}_daily_3d'
        ).write_text(f'{variant}\n')
    script = case_dir / 'next_segment.sh'
    script.write_text(
        get_next_segment_script(
            experiment,
            get_segments(experiment, 48 if experiment != 'ocean1' else 12),
        )
    )
    for name in ['xmlquery', 'xmlchange', 'next_segment.sh']:
        (case_dir / name).chmod(0o755)
    return case_dir


def _next_segment(case_dir, restart_date=None, start=False):
    if restart_date is not None:
        rundir = (case_dir / 'xml/RUNDIR').read_text()
        with open(os.path.join(rundir, 'rpointer.drv'), 'w') as pointer:
            # The coupler pads the file name with spaces.
            name = f'case.cpl.r.{restart_date}-00000.nc'
            pointer.write(f'{name:<256}\n')
    args = [str(case_dir / 'next_segment.sh'), str(case_dir)]
    if start:
        args.append('--start')
    return subprocess.run(args, text=True, capture_output=True)


def _xml(case_dir, variable):
    return (case_dir / 'xml' / variable).read_text()


def _streams(case_dir):
    return (case_dir / 'SourceMods/src.mpaso/streams.ocean').read_text()


def test_readme_describes_the_segments():
    text = get_readme(
        'iceocean1r',
        GRIDS,
        ['layout: 64 tasks'],
        segments=get_segments('iceocean1r', 48),
    )
    text = ' '.join(text.split())
    assert (
        'The case runs 1200 months in 27 jobs: 12 months, 24 of 48 months, '
        '24 months and 12 months'
    ) in text
    assert 'in its first and last 12 months' in text
    for name in ['postrun.local', 'next_segment.skip', 'RESUBMIT=0']:
        assert name in text


def test_next_segment_script_passes_bash_syntax_check():
    text = get_next_segment_script(
        'iceocean1r', get_segments('iceocean1r', 48)
    )
    result = subprocess.run(
        ['bash', '-n'], input=text, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr


def test_next_segment_sets_up_each_job(tmp_path):
    case_dir = _fake_case(tmp_path, RESUBMIT='30')
    # before the first job: the first year, with daily 3D fields, and the
    # jobs after it
    result = _next_segment(case_dir, start=True)
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '12'
    assert _xml(case_dir, 'RESUBMIT') == '26'
    assert _streams(case_dir) == 'with\n'

    postrun = case_dir / 'postrun.local'
    postrun.write_text('#!/bin/bash\necho "$1" >> "$1/postrun.ran"\n')
    postrun.chmod(0o755)

    # after the first year
    result = _next_segment(case_dir, '0002-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '48'
    assert _streams(case_dir) == 'without\n'
    assert _xml(case_dir, 'RESUBMIT') == '26'
    assert (case_dir / 'postrun.ran').read_text() == f'{case_dir}\n'

    # a rerun changes nothing
    changes = (case_dir / 'changes').read_text()
    result = _next_segment(case_dir, '0002-01-01')
    assert result.returncode == 0, result.stderr
    assert (case_dir / 'changes').read_text() == changes

    # 2 years, then the last year with daily 3D fields
    result = _next_segment(case_dir, '0098-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '24'
    assert _streams(case_dir) == 'without\n'
    result = _next_segment(case_dir, '0100-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '12'
    assert _streams(case_dir) == 'with\n'
    # a resubmission lowers RESUBMIT, but a lower one is kept
    assert _xml(case_dir, 'RESUBMIT') == '1'

    # done
    result = _next_segment(case_dir, '0101-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'RESUBMIT') == '0'
    log = (case_dir / 'next_segment.log').read_text()
    assert 'STOP_N: 12 -> 48' in log
    assert 'streams.ocean: with_daily_3d' in log
    assert 'All 1200 months are run.' in log


def test_next_segment_keeps_a_stopped_chain(tmp_path):
    case_dir = _fake_case(tmp_path, RESUBMIT='0')
    result = _next_segment(case_dir, '0002-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'RESUBMIT') == '0'


def test_next_segment_branch_run_counts_from_its_start(tmp_path):
    case_dir = _fake_case(
        tmp_path,
        experiment='iceocean1ra',
        RUN_TYPE='branch',
        RUN_REFDATE='0101-01-01',
    )
    result = _next_segment(case_dir, '0102-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '48'
    assert _streams(case_dir) == 'without\n'


@pytest.mark.parametrize(
    'restart_date, match',
    [
        ('0002-01-15', 'not on the first of a month'),
        ('0003-01-01', 'does not start a segment'),
    ],
)
def test_next_segment_stops_the_chain(tmp_path, restart_date, match):
    case_dir = _fake_case(tmp_path)
    result = _next_segment(case_dir, restart_date)
    assert result.returncode != 0
    assert match in result.stderr
    assert match in (case_dir / 'next_segment.log').read_text()
    assert _xml(case_dir, 'STOP_N') == '12'


def test_next_segment_stops_without_a_restart_pointer(tmp_path):
    case_dir = _fake_case(tmp_path)
    result = _next_segment(case_dir)
    assert result.returncode != 0
    assert 'no restart pointer' in result.stderr


def test_next_segment_refuses_a_shared_source_mods(tmp_path):
    case_dir = _fake_case(tmp_path)
    (tmp_path / 'base_source_mods').mkdir()
    os.symlink(tmp_path / 'base_source_mods', case_dir / 'SourceMods')
    result = _next_segment(case_dir, '0002-01-01')
    assert result.returncode != 0
    assert 'keepexe' in result.stderr


def test_next_segment_can_be_skipped(tmp_path):
    case_dir = _fake_case(tmp_path)
    (case_dir / 'next_segment.skip').write_text('')
    postrun = case_dir / 'postrun.local'
    postrun.write_text('#!/bin/bash\ntouch "$1/postrun.ran"\n')
    postrun.chmod(0o755)
    # even a date that would stop the chain
    result = _next_segment(case_dir, '0003-01-01')
    assert result.returncode == 0, result.stderr
    assert _xml(case_dir, 'STOP_N') == '12'
    assert not (case_dir / 'changes').exists()
    assert (case_dir / 'postrun.ran').exists()
