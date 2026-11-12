import json
import os

from polaris import Component
from polaris.analysis.page import PAGE_FILENAME
from polaris.e3sm.analysis.case import E3smCase
from polaris.e3sm.analysis.provenance import (
    CaseProvenance,
    has_local_changes,
    read_case_commands,
    read_namelist_groups,
    read_restart_date,
    read_user_namelist,
    xmlchange_variables,
)
from tests.e3sm.analysis.test_case import _write_case

CASE = 'test.case'

REPLAY = """#!/bin/bash
set -e
# Created 2026-11-11 02:40:52
CASEDIR="/cases/test.case"
/e3sm/cime/scripts/create_newcase --case "${CASEDIR}" --compset C --res R
cd "${CASEDIR}"
./xmlchange --force 'MPASO_IC_FILE=$DIN_LOC_ROOT/ocn/ic.nc'
./xmlchange NCPL_BASE_PERIOD=day,OCN_NCPL=48
./xmlchange --force JOB_WALLCLOCK_TIME=24:00:00 --subgroup case.run
./xmlchange NTASKS_GLC=128
./case.setup
./xmlchange STOP_N=48
"""

USER_NL_MPASO = """! The standalone run's options

! time_integration
config_dt = '0000_00:01:00.000'
config_time_integrator = 'split_explicit'  ! the split's own comment
config_note = 'a ! in quotes'
"""

ENV_BATCH = """<?xml version="1.0"?>
<file id="env_batch.xml" version="2.0">
  <group id="case.run">
    <entry id="JOB_WALLCLOCK_TIME" value="24:00:00"/>
  </group>
  <group id="case.st_archive">
    <entry id="JOB_WALLCLOCK_TIME" value="00:20:00"/>
  </group>
</file>
"""

ENV_MACH_PES = """<?xml version="1.0"?>
<file id="env_mach_pes.xml" version="2.0">
  <group id="mach_pes">
    <entry id="NTASKS">
      <values>
        <value compclass="OCN">256</value>
        <value compclass="GLC">128</value>
      </values>
    </entry>
  </group>
</file>
"""

MPASO_IN = """&time_integration
    config_dt = '0000_00:01:00.000'
    config_time_integrator = 'split_explicit'
/
&misc
    config_note = 'a ! in quotes'
/
"""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as out:
        out.write(text)


def _make_case(tmp_path):
    case_dir = str(tmp_path / 'cases' / CASE)
    run_dir = str(tmp_path / 'scratch' / CASE / 'run')
    build_dir = str(tmp_path / 'scratch' / CASE / 'bld')
    _write_case(
        case_dir,
        {
            'env_case.xml': {
                'CASE': CASE,
                'COMPSET': 'C',
                'MACH': 'chrysalis',
                'SRCROOT': '/e3sm',
            },
            'env_build.xml': {
                'EXEROOT': build_dir,
                'COMPILER': 'gnu',
                'MPILIB': 'openmpi',
            },
            'env_run.xml': {
                'RUNDIR': run_dir,
                'RUN_TYPE': 'startup',
                'STOP_N': '48',
                'OCN_NCPL': '48',
                'NCPL_BASE_PERIOD': 'day',
                'MPASO_IC_FILE': '/inputdata/ocn/ic.nc',
            },
        },
    )
    # a variable with a value for each job
    _write(os.path.join(case_dir, 'env_batch.xml'), ENV_BATCH)
    _write(os.path.join(case_dir, 'env_mach_pes.xml'), ENV_MACH_PES)
    _write(os.path.join(case_dir, 'replay.sh'), REPLAY)
    _write(os.path.join(case_dir, 'user_nl_mpaso'), USER_NL_MPASO)
    _write(os.path.join(case_dir, 'user_nl_cpl'), '! only comments\n')
    _write(
        os.path.join(case_dir, 'SourceMods', 'src.mpaso', 'streams.ocean'),
        '<streams/>\n',
    )
    _write(os.path.join(case_dir, 'SourceMods', 'src.mpaso', 'README'), '')
    _write(os.path.join(run_dir, 'mpaso_in'), MPASO_IN)
    _write(os.path.join(run_dir, 'streams.ocean'), '<streams/>\n')
    _write(os.path.join(run_dir, 'albany_input.yaml'), 'ANONYMOUS:\n')
    _write(
        os.path.join(run_dir, 'rpointer.drv'),
        f'{CASE}.cpl.r.0006-01-01-00000.nc\n',
    )
    _write(os.path.join(build_dir, 'GIT_DESCRIBE'), 'v3.2.0-1-gabc1234')
    _write(
        os.path.join(build_dir, 'GIT_LOG'),
        'abc1234 Merge the fix\n0123456 Earlier\n',
    )
    _write(os.path.join(build_dir, 'GIT_DIFF'), "Entering 'cime'\n\n")
    _write(
        os.path.join(build_dir, 'build_environment.txt'),
        'Currently Loaded Modules:\nAlbany_ROOT=/soft/albany/2026.05.26\n',
    )
    return E3smCase(case_dir)


def test_the_commands_and_the_variables_they_set_are_read(tmp_path):
    filename = str(tmp_path / 'replay.sh')
    _write(filename, REPLAY)

    commands = read_case_commands(filename)

    assert commands[0] == 'CASEDIR="/cases/test.case"'
    assert commands[-1] == './xmlchange STOP_N=48'
    assert xmlchange_variables(commands) == [
        'MPASO_IC_FILE',
        'NCPL_BASE_PERIOD',
        'OCN_NCPL',
        'JOB_WALLCLOCK_TIME',
        'NTASKS_GLC',
        'STOP_N',
    ]
    assert xmlchange_variables(['./xmlchange --id STOP_N --val 1']) == [
        'STOP_N'
    ]


def test_user_namelist_options_and_their_groups_are_read(tmp_path):
    user_nl = str(tmp_path / 'user_nl_mpaso')
    namelist = str(tmp_path / 'mpaso_in')
    _write(user_nl, USER_NL_MPASO)
    _write(namelist, MPASO_IN)

    assert read_user_namelist(user_nl) == [
        ('config_dt', "'0000_00:01:00.000'"),
        ('config_time_integrator', "'split_explicit'"),
        ('config_note', "'a ! in quotes'"),
    ]
    assert read_namelist_groups(namelist) == {
        'config_dt': 'time_integration',
        'config_time_integrator': 'time_integration',
        'config_note': 'misc',
    }


def test_a_diff_of_only_submodule_names_has_no_changes(tmp_path):
    filename = str(tmp_path / 'GIT_DIFF')
    _write(filename, "Entering 'cime'\n\nEntering 'components/x'\n")
    assert not has_local_changes(filename)
    _write(filename, 'diff --git a/x b/x\n')
    assert has_local_changes(filename)


def test_the_latest_restart_date_is_read(tmp_path):
    filename = str(tmp_path / 'rpointer.drv')
    assert read_restart_date(filename) is None
    _write(filename, 'case.cpl.r.0006-01-01-00000.nc\n')
    assert read_restart_date(filename) == '0006-01-01-00000'


def test_the_step_describes_and_copies_the_case(tmp_path):
    case = _make_case(tmp_path)
    step = CaseProvenance(
        component=Component(name='e3sm'), subdir='a/provenance', case=case
    )
    assert PAGE_FILENAME in step.outputs
    step.work_dir = str(tmp_path / 'work')
    os.makedirs(step.work_dir)

    step.run()

    with open(os.path.join(step.work_dir, PAGE_FILENAME)) as data:
        page = json.load(data)
    assert page['name'] == 'provenance'
    sections = {section['title']: section for section in page['sections']}
    code = {entry['label']: entry for entry in sections['Code']['entries']}
    assert code['E3SM version']['value'] == 'v3.2.0-1-gabc1234'
    assert code['E3SM commit']['value'] == 'abc1234 Merge the fix'
    assert code['local changes']['value'] == 'none'
    assert code['Albany']['value'] == '/soft/albany/2026.05.26'
    assert 'Trilinos' not in code
    changed = sections['Case variables changed']['table']['rows']
    assert [row[0]['value'] for row in changed] == [
        'MPASO_IC_FILE',
        'NCPL_BASE_PERIOD',
        'OCN_NCPL',
        'JOB_WALLCLOCK_TIME',
        'NTASKS_GLC',
        'STOP_N',
    ]
    assert changed[0][1]['value'] == '/inputdata/ocn/ic.nc'
    assert changed[3][1]['value'] == (
        'case.run: 24:00:00; case.st_archive: 00:20:00'
    )
    assert changed[4][1]['value'] == '128'
    options = sections['Options set in user_nl_mpaso']['table']['rows']
    assert [[cell['value'] for cell in row] for row in options][0] == [
        'time_integration',
        'config_dt',
        "'0000_00:01:00.000'",
    ]
    # a user namelist that sets nothing gets no section
    assert 'Options set in user_nl_cpl' not in sections
    source_mods = sections['SourceMods']['table']['rows']
    assert [row[1]['value'] for row in source_mods] == ['streams.ocean']
    files = sections['Files the models read']
    assert '0006-01-01-00000' in files['text']
    assert [entry['label'] for entry in files['entries']] == [
        'mpaso_in',
        'streams.ocean',
        'albany_input.yaml',
    ]
    assert page['files']['files/mpaso_in'] == 'mpaso_in.txt'
    assert page['files']['files/build_environment.txt'] == (
        'build_environment.txt'
    )
    for local in page['files']:
        assert os.path.isfile(os.path.join(step.work_dir, local))
