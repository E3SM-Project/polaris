import os
import re
import subprocess
import xml.etree.ElementTree as ET
from glob import glob

import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.misomip import get_misomip_experiment_steps
from polaris.tasks.e3sm.init.misomip.case_config import (
    COMPONENTS,
    DIN_LOC_ROOT,
    E3SM_COMMIT,
    E3SM_DEFAULT_OPTIONS,
    E3SM_OWNED_OPTIONS,
    get_create_case_script,
    get_grid_file,
    get_inputdata_root,
    get_pes_file,
    get_readme,
    get_shell_commands,
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
    assert (
        f"./xmlchange 'MPASO_IC_FILE=/short/inputdata/ocn/mpas-o/"
        f"misomip-o4km/mpaso.misomip-o4km.ocean0.{DATE}.nc'"
    ) in text.splitlines()
    assert './xmlchange RESUBMIT=11' in text.splitlines()


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
    'experiment, has_case_config',
    [
        ('ocean0', True),
        ('ocean3', True),
        ('iceocean1r', False),
        ('iceocean1ra', False),
    ],
)
def test_experiments_with_a_standalone_run_have_a_case_config(
    experiment, has_case_config
):
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, experiment)
    assert ('case_config' in steps) == has_case_config
    if has_case_config:
        step = steps['case_config']
        assert step.path == (
            f'e3sm/init/{MESH_NAME}/misomip/{experiment}/case_config'
        )
        targets = {
            entry['filename']: entry['work_dir_target']
            for entry in step.input_data
        }
        assert targets['namelist.ocean'] == (
            f'ocean/planar/misomip/{MESH_NAME}/{experiment}/forward/'
            f'namelist.ocean'
        )
        assert targets['ocean.cfg'] == (
            f'ocean/planar/misomip/{MESH_NAME}/{experiment}/misomip_ocean.cfg'
        )
        assert 'case_config' in steps['assemble'].product_steps
