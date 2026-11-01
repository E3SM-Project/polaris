import gzip
import os

import pytest

from polaris.e3sm.analysis.case import E3smCase

CASE = 'test.case'

STREAMS_OCEAN = f"""<streams>
<stream name="timeSeriesStatsMonthlyOutput"
        type="output"
        filename_template="{CASE}.mpaso.hist.am.timeSeriesStatsMonthly.$Y-$M-$D.nc"
        output_interval="00-01-00_00:00:00">
    <var name="xtime"/>
</stream>
</streams>
"""


def _write_case(case_dir, entries):
    """Write the env_*.xml files of a case, in the form CIME writes"""
    os.makedirs(case_dir, exist_ok=True)
    for filename, file_entries in entries.items():
        lines = [
            '<?xml version="1.0"?>',
            f'<file id="{filename}" version="2.0">',
            '  <group id="test">',
        ]
        for name, value in file_entries.items():
            lines.append(f'    <entry id="{name}" value="{value}">')
            lines.append('      <type>char</type>')
            lines.append('    </entry>')
        lines += ['  </group>', '</file>', '']
        with open(os.path.join(case_dir, filename), 'w') as out:
            out.write('\n'.join(lines))


def _make_case(tmp_path, monkeypatch):
    monkeypatch.setenv('USER', 'tester')
    output_root = str(tmp_path / 'scratch')
    case_dir = str(tmp_path / 'cases' / CASE)
    _write_case(
        case_dir,
        {
            'env_case.xml': {'CASE': CASE, 'USER': '$ENV{USER}'},
            'env_run.xml': {
                'CIME_OUTPUT_ROOT': output_root,
                'RUNDIR': '$CIME_OUTPUT_ROOT/$CASE/run',
                'DOUT_S_ROOT': f'{output_root}/$USER/archive/${{CASE}}',
                'MALI_PROGNOSTIC_MODE': 'STATIC',
            },
        },
    )
    return E3smCase(case_dir)


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w'):
        pass


def test_case_variables_expand_their_references(tmp_path, monkeypatch):
    """References to other case variables, in either form, and to the
    environment in CIME's $ENV{} form are all expanded."""
    case = _make_case(tmp_path, monkeypatch)

    assert case.case_name == CASE
    assert case.run_dir == str(tmp_path / 'scratch' / CASE / 'run')
    assert case.archive_dir == str(
        tmp_path / 'scratch' / 'tester' / 'archive' / CASE
    )
    assert case.landice_mode == 'static'


def test_an_unknown_variable_is_an_error(tmp_path, monkeypatch):
    case = _make_case(tmp_path, monkeypatch)

    with pytest.raises(KeyError, match='NOT_A_VARIABLE'):
        case.get_value('NOT_A_VARIABLE')


def test_variables_that_refer_to_each_other_are_an_error(tmp_path):
    case_dir = str(tmp_path / 'case')
    _write_case(case_dir, {'env_run.xml': {'A': '$B', 'B': '$A'}})
    case = E3smCase(case_dir)

    with pytest.raises(ValueError, match='A -> B -> A'):
        case.get_value('A')


def test_a_directory_without_env_files_is_not_a_case(tmp_path):
    with pytest.raises(FileNotFoundError, match='not an E3SM case'):
        E3smCase(str(tmp_path))


def test_stream_files_are_found_in_the_archive_then_the_run(
    tmp_path, monkeypatch
):
    """Short-term archiving moves the older files; the newest month is still
    in the run directory."""
    case = _make_case(tmp_path, monkeypatch)
    os.makedirs(case.run_dir)
    with open(os.path.join(case.run_dir, 'streams.ocean'), 'w') as out:
        out.write(STREAMS_OCEAN)
    prefix = f'{CASE}.mpaso.hist.am.timeSeriesStatsMonthly'
    archived = os.path.join(case.archive_dir, 'ocn', 'hist')
    _touch(os.path.join(archived, f'{prefix}.0001-01-01.nc'))
    _touch(os.path.join(case.run_dir, f'{prefix}.0001-02-01.nc'))

    files = case.find_stream_files('mpaso', 'timeSeriesStatsMonthlyOutput')

    assert [(f.month, os.path.dirname(f.path)) for f in files] == [
        (1, archived),
        (2, case.run_dir),
    ]


def test_logs_are_found_compressed_and_in_either_place(tmp_path, monkeypatch):
    case = _make_case(tmp_path, monkeypatch)
    archived = os.path.join(case.archive_dir, 'logs', 'cpl.log.100.1-1.gz')
    os.makedirs(os.path.dirname(archived))
    with gzip.open(archived, 'wt') as out:
        out.write('archived')
    _touch(os.path.join(case.run_dir, 'cpl.log.200.1-2.gz'))
    _touch(os.path.join(case.run_dir, 'ocn.log.200.1-2.gz'))

    logs = case.find_logs('cpl')

    assert [os.path.basename(log) for log in logs] == [
        'cpl.log.100.1-1.gz',
        'cpl.log.200.1-2.gz',
    ]


def test_an_unknown_model_is_an_error(tmp_path, monkeypatch):
    case = _make_case(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match='mpaso, mali'):
        case.read_streams('cice')
