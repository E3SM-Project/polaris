import dataclasses
import json
from pathlib import Path

import polaris_update_report
import polaris_update_setup
import polaris_update_status
import pr_test_github
import pr_test_report
import pr_test_setup
import pytest
from polaris_update_manifest import MARKER_PREFIX, OmegaMerge
from update_fixtures import load_env, make_tester, write_load_script

SUITE_MD = {
    'mpaso_pr': '### Polaris `mpaso_pr` suite\n- Result: All tests passed\n',
    'omega_pr': '### Polaris `omega_pr` suite\n- Result: All tests passed\n',
}

CTEST_MD = '### CTest unit tests:\n- Result: All tests passed\n'


@pytest.fixture
def finished(tmp_path, monkeypatch):
    """chrysalis/gnu's two rows, set up against main and finished"""
    fixture, manifest, _ = make_tester(tmp_path, monkeypatch)
    load_script = write_load_script(
        tmp_path / 'load_main.sh', fixture.baseline_dir
    )
    states = polaris_update_setup.run_setup(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        baseline_load_script=load_script,
        polaris_dir=fixture.polaris_dir,
    )
    for state, _ in states:
        _finish(state)
    return fixture, manifest


def test_report(finished):
    fixture, manifest = finished

    text, path = _report(fixture, manifest, not_run='the intel queue is down')

    assert text.startswith(
        '## Testing on chrysalis with the shared Spack environments\n'
    )
    assert (
        f'Tested E3SM-Project/polaris#835 (`{fixture.pr_head[:10]}`), '
        f'Polaris 1.2.0-alpha.1 with mache '
    ) in text
    assert '`/shared/spack/dev_polaris_1.2.0`' in text
    assert (
        f'The baseline is `{fixture.main[:10]}`, Polaris 1.1.0-alpha.7'
    ) in text
    assert (
        '| chrysalis, gnu, openmpi (MPAS-Ocean) | `mpaso_pr`: 3 of 3 passed '
        '|  |  |'
    ) in text
    assert (
        '| chrysalis, intel, openmpi (Omega) | not run: the intel queue is '
        'down |  |  |'
    ) in text
    assert (
        '| chrysalis, gnu, openmpi (Omega) | `omega_pr`: 3 of 3 passed | 50 '
        'of 50 passed | not compared |'
    ) in text
    assert (
        '### Bit-for-bit with the baseline\n\nEvery task compared with the '
        'baseline is bit-for-bit (6 tasks).'
    ) in text
    assert (
        '- chrysalis, intel, openmpi (Omega): not compared, because it was '
        'not run: the intel queue is down.'
    ) in text
    assert (
        '- chrysalis, gnu, openmpi (MPAS-Ocean), `mpaso_pr`: 3 of 3 tasks '
        'that ran are bit-for-bit.'
    ) in text
    block = text.split('<summary>chrysalis, gnu, openmpi (Omega)</summary>')
    assert SUITE_MD['omega_pr'].strip() in block[1]
    assert CTEST_MD.strip() in block[1]

    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert marker['spack'] == 'shared'
    assert [(row['row'], row['status']) for row in marker['rows']] == [
        ('chrysalis/gnu/mpas-ocean', 'complete'),
        ('chrysalis/intel/omega', 'not-run'),
        ('chrysalis/gnu/omega', 'complete'),
    ]
    run_dir = Path(fixture.config.work_base) / manifest.run_name
    assert Path(path) == run_dir / 'shared' / 'report_chrysalis.md'


def test_describe_omega_merge(finished):
    _, manifest = finished
    merge = OmegaMerge('m' * 40, {600: 'f' * 40}, 'e3sm-fork', 'branch')

    text = polaris_update_report.describe(
        dataclasses.replace(manifest, omega_merge=merge), 'shared', []
    )

    assert (
        f'Omega `{manifest.test.omega_commit[:10]}` with '
        f'E3SM-Project/Omega#600 merged in (`mmmmmmmmmm`)'
    ) in text


def test_describe_mache_branch(finished):
    _, manifest = finished
    state = pr_test_setup.SetupState(
        fork='fork',
        branch='branch',
        row='chrysalis/gnu/openmpi',
        polaris_hash='p' * 40,
        baseline_work_dir=None,
        baseline_reused=False,
        baseline_job=None,
        baseline_build_log=None,
        pr_build_dir='build',
        pr_work_dir='work',
        ctest_dir=None,
        environment={'mache_version': '5.3.0', 'mache_source': 'branch'},
    )

    text = polaris_update_report.describe(manifest, 'shared', [state])

    assert 'Polaris 1.2.0-alpha.1 with mache 5.3.0 from a branch, ' in text


def test_report_not_bit_for_bit(finished):
    fixture, manifest = finished
    run_dir = Path(fixture.config.work_base) / manifest.run_name / 'shared'
    results = (
        run_dir / 'chrysalis_gnu_omega' / 'omega_pr' / 'omega_pr_results.json'
    )
    contents = json.loads(results.read_text())
    contents['tasks'][0].update(
        {
            'status': 'fail',
            'baseline': 'fail',
            'baseline_diffs': {
                'normalVelocity': {'l1': 1e-12, 'l2': 1e-13, 'linf': 1e-14},
                'temperature': {'l1': 0.0, 'l2': 0.0, 'linf': 0.0},
                'layerThickness': {'l1': 'NaN', 'l2': 'NaN', 'linf': 'NaN'},
            },
        }
    )
    contents['tasks'][1].update({'status': 'fail', 'execution': 'fail'})
    results.write_text(json.dumps(contents))

    text, _ = _report(fixture, manifest, not_run='down')

    assert '**Not bit-for-bit: 1 task, on 1 row.**' in text
    assert (
        '1 task did not run, so it has no bit-for-bit result either way.'
    ) in text
    assert (
        '  - Not bit-for-bit: `ocean/task0` (`layerThickness`, '
        '`normalVelocity`)'
    ) in text
    assert '  - Did not run: `ocean/task1`' in text
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    omega = [
        row for row in marker['rows'] if row['row'] == 'chrysalis/gnu/omega'
    ]
    assert (omega[0]['non_bfb'], omega[0]['did_not_run']) == (1, 1)


def test_report_needs_every_row(finished):
    fixture, manifest = finished
    with pytest.raises(
        pr_test_report.ReportError, match='chrysalis/intel/omega'
    ):
        _report(fixture, manifest)


def test_report_kind_of_environment(finished, monkeypatch):
    fixture, manifest = finished
    load_env(monkeypatch, fixture, 'chrysalis', 'gnu', 'openmpi', view='')

    with pytest.raises(pr_test_report.ReportError, match='--spack'):
        _report(fixture, manifest, not_run='down')

    # off the machines, with nothing loaded, a machine that was not run
    text, _ = _report(
        fixture,
        manifest,
        machine='pm-cpu',
        spack='test',
        not_run='Perlmutter is down',
    )
    assert text.startswith(
        '## Testing on pm-cpu and pm-gpu with the test Spack environments\n'
    )


def test_status(finished, monkeypatch):
    fixture, manifest = finished
    text, _ = _report(fixture, manifest, not_run='down')
    monkeypatch.setattr(
        pr_test_github, 'get_comment_bodies', lambda repo, number: [text]
    )
    monkeypatch.setattr(
        pr_test_github,
        'get_pull_request',
        lambda repo, number: {'headRefOid': fixture.pr_head},
    )
    monkeypatch.setattr(
        polaris_update_status.status, 'discover_machine', lambda quiet: None
    )

    lines = polaris_update_status.run_status(835, manifest).splitlines()

    rows = {line.split()[0]: line for line in lines[1:] if line.strip()}
    assert 'pass' in rows['chrysalis/gnu/mpas-ocean/shared']
    assert 'not run' in rows['chrysalis/intel/omega/shared']
    assert rows['pm-gpu/gnugpu/omega/shared'].split()[1] == '-'
    # only the kind of environment that has been reported on is listed
    assert not any(name.endswith('/test') for name in rows)


def _report(fixture, manifest, **kwargs):
    return polaris_update_report.run_report(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )


def _finish(state):
    """What the PR suite and CTest jobs leave behind"""
    work_dir = Path(state.pr_work_dir)
    (work_dir / f'{state.suite}_output_for_pr.md').write_text(
        SUITE_MD[state.suite]
    )
    tasks = [
        {
            'path': f'ocean/task{index}',
            'status': 'pass',
            'execution': 'pass',
            'baseline': 'pass',
        }
        for index in range(3)
    ]
    (work_dir / f'{state.suite}_results.json').write_text(
        json.dumps(
            {
                'complete': True,
                'summary': {'total': 3, 'passed': 3, 'failed': 0},
                'tasks': tasks,
            }
        )
    )
    if state.ctest_dir is not None:
        build_dir = Path(state.pr_build_dir)
        (build_dir / 'ctest_output_for_pr.md').write_text(CTEST_MD)
        (build_dir / 'ctests.log').write_text(
            '100% tests passed, 0 tests failed out of 50\n'
        )
