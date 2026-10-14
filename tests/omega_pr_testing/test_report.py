import dataclasses
import json
from pathlib import Path

import omega_pr_report
import omega_pr_setup
import pr_test_github
import pr_test_report
import pytest
from omega_pr_fixtures import make_tester
from omega_pr_manifest import MARKER_PREFIX, UPSTREAM

SUITE_MD = """### Polaris `omega_pr` suite
- Baseline workdir: `/baseline`
- PR build: `/pr/build`
- Polaris: `aaaa` (`1.0.0-801-gaaaa`)
- Result: All tests passed
"""

CTEST_MD = """### CTest unit tests:
- Machine: `chrysalis`
- Compiler: `intel`
- Result: All tests passed
"""

URL = 'https://github.com/E3SM-Project/Omega/pull/5#comment'


@pytest.fixture
def tester(tmp_path, monkeypatch):
    return make_tester(tmp_path, monkeypatch)


@pytest.fixture
def finished(tester):
    """A row that setup prepared and whose jobs have finished"""
    fixture, manifest, _ = tester
    state = _setup(fixture, manifest)
    _finish(state)
    return fixture, manifest, state


def test_report(finished):
    fixture, manifest, state = finished

    text, url, path = omega_pr_report.run_report(
        fixture.config, fixture.fork, manifest.branch, agent='Claude Code'
    )

    assert url is None
    assert text.startswith('## Testing on chrysalis\n')
    assert (
        f'Tested the merge of E3SM-Project/Omega#5 '
        f'(`{manifest.pr_head[:10]}`) into `develop` '
        f'(`{manifest.base_head[:10]}`) as `{manifest.test_commit[:10]}`, '
        f"against Polaris' Omega submodule "
        f'(`{manifest.baseline_commit[:10]}`).'
    ) in text
    assert (
        '| chrysalis, intel, openmpi | 50 of 50 passed | 3 of 3 passed | 0 |'
    ) in text
    # both files are pasted as they are, in the row's collapsed block
    block = text.split('<summary>chrysalis, intel, openmpi</summary>')[1]
    assert SUITE_MD.strip() in block
    assert CTEST_MD.strip() in block
    assert 'No new warnings (0 in the PR build, 0 in the baseline build)' in (
        block
    )
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert marker['schema'] == 2
    assert marker['pr_head'] == manifest.pr_head
    assert marker['rows'] == [
        {
            'row': 'chrysalis/intel',
            'status': 'complete',
            'result': 'pass',
            'new_warnings': 0,
        }
    ]
    run_dir = Path(fixture.config.work_base) / manifest.run_name
    assert Path(path) == run_dir / 'report_chrysalis.md'


def test_report_shares_login_nodes(tester, monkeypatch):
    fixture, manifest, _ = tester
    for machine, compiler in [('pm-cpu', 'gnu'), ('pm-gpu', 'gnugpu')]:
        _set_env(monkeypatch, machine, compiler, 'mpich')
        _finish(_setup(fixture, manifest))

    text, _, path = omega_pr_report.run_report(
        fixture.config, fixture.fork, manifest.branch
    )

    assert text.startswith('## Testing on pm-cpu and pm-gpu\n')
    assert '| pm-cpu, gnu, mpich | 50 of 50 passed |' in text
    assert '| pm-gpu, gnugpu, mpich | 50 of 50 passed |' in text
    assert text.count(SUITE_MD.strip()) == 2
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert [row['row'] for row in marker['rows']] == [
        'pm-cpu/gnu',
        'pm-gpu/gnugpu',
    ]
    assert Path(path).name == 'report_pm-cpu_pm-gpu.md'


def test_report_without_baseline(tester):
    fixture, manifest, _ = tester
    _finish(_setup(fixture, manifest, no_baseline='develop cannot run'))

    text, _, _ = omega_pr_report.run_report(
        fixture.config, fixture.fork, manifest.branch
    )

    assert (
        '| chrysalis, intel, openmpi | 50 of 50 passed | 3 of 3 passed, '
        'without a baseline | not compared |'
    ) in text
    assert (
        'Not compared: this row ran without a baseline, because develop '
        'cannot run.'
    ) in text
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert marker['rows'][0]['no_baseline'] == 'develop cannot run'


def test_report_baseline_polaris(finished):
    _, manifest, _ = finished
    assert 'The baseline ran' not in omega_pr_report.describe_commits(manifest)

    other = dataclasses.replace(manifest, baseline_polaris_commit='b' * 40)
    assert (
        f'The baseline ran with Polaris `bbbbbbbbbb`, without the changes '
        f'in Polaris `{manifest.polaris_commit[:10]}` that the PR needs.'
    ) in omega_pr_report.describe_commits(other)


def test_report_failures(finished):
    fixture, manifest, state = finished
    results = Path(state.pr_work_dir, 'omega_pr_results.json')
    contents = json.loads(results.read_text())
    contents['summary'].update({'passed': 2, 'failed': 1})
    contents['tasks'][0]['baseline'] = 'fail'
    results.write_text(json.dumps(contents))
    Path(state.pr_build_dir, 'ctests.log').write_text(
        '98% tests passed, 1 tests failed out of 50\n'
    )

    text, _, _ = omega_pr_report.run_report(
        fixture.config, fixture.fork, manifest.branch
    )

    assert (
        '| chrysalis, intel, openmpi | 49 of 50 passed | 2 of 3 passed, 1 '
        'with baseline differences | 0 |'
    ) in text
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None and marker['rows'][0]['result'] == 'fail'


def test_report_before_the_jobs_finish(finished):
    fixture, manifest, state = finished
    Path(state.pr_work_dir, 'omega_pr_output_for_pr.md').unlink()

    with pytest.raises(
        pr_test_report.ReportError, match='chrysalis/intel: .*not finished'
    ):
        omega_pr_report.run_report(
            fixture.config, fixture.fork, manifest.branch
        )


def test_report_not_run(finished):
    fixture, manifest, _ = finished

    text, _, path = omega_pr_report.run_report(
        fixture.config,
        fixture.fork,
        manifest.branch,
        machine='aurora',
        not_run='Aurora is down for maintenance',
    )

    assert text.startswith('## Testing on aurora\n')
    assert (
        '| aurora, intel, mpich (Polaris `oneapi-ifx`) | not run: Aurora is '
        'down for maintenance |  |  |'
    ) in text
    assert '<details>' not in text
    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert [(row['row'], row['status']) for row in marker['rows']] == [
        ('aurora/oneapi-ifx', 'not-run'),
        ('aurora/oneapi-ifxgpu', 'not-run'),
    ]
    assert Path(path).name == 'report_aurora.md'


def test_report_some_rows_not_run(tester, monkeypatch):
    fixture, manifest, _ = tester
    _set_env(monkeypatch, 'pm-cpu', 'gnu', 'mpich')
    _finish(_setup(fixture, manifest))

    with pytest.raises(pr_test_report.ReportError, match='pm-gpu/gnugpu'):
        omega_pr_report.run_report(
            fixture.config, fixture.fork, manifest.branch
        )

    text, _, _ = omega_pr_report.run_report(
        fixture.config,
        fixture.fork,
        manifest.branch,
        not_run='the GPU queue is down',
    )

    marker = pr_test_report.parse_marker(text, MARKER_PREFIX)
    assert marker is not None
    assert [(row['row'], row['status']) for row in marker['rows']] == [
        ('pm-cpu/gnu', 'complete'),
        ('pm-gpu/gnugpu', 'not-run'),
    ]


def test_post_file(finished, tmp_path, monkeypatch):
    fixture, manifest, _ = finished
    _, _, path = omega_pr_report.run_report(
        fixture.config, fixture.fork, manifest.branch
    )
    posted = _mock_post(monkeypatch)

    assert pr_test_report.post_file(UPSTREAM, 5, path, MARKER_PREFIX) == URL
    assert posted == [(UPSTREAM, 5, path)]

    with pytest.raises(ValueError, match='for PR 5, not 6'):
        pr_test_report.post_file(UPSTREAM, 6, path, MARKER_PREFIX)
    other = tmp_path / 'other.md'
    other.write_text('## Testing: by hand\n')
    with pytest.raises(ValueError, match='no omega-pr-test marker'):
        pr_test_report.post_file(UPSTREAM, 5, str(other), MARKER_PREFIX)
    assert len(posted) == 1


def _setup(fixture, manifest, **kwargs):
    return omega_pr_setup.run_setup(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )


def _set_env(monkeypatch, machine, compiler, mpi):
    """Load the Polaris environment of another row"""
    monkeypatch.setenv('POLARIS_MACHINE', machine)
    monkeypatch.setenv('POLARIS_COMPILER', compiler)
    monkeypatch.setenv('POLARIS_MPI', mpi)


def _mock_post(monkeypatch):
    posted = []

    def post_comment(repo, number, body_file):
        posted.append((repo, number, body_file))
        return URL

    monkeypatch.setattr(pr_test_github, 'post_comment', post_comment)
    return posted


def _finish(state):
    """What the PR suite and CTest jobs leave behind"""
    work_dir = Path(state.pr_work_dir)
    (work_dir / 'omega_pr_output_for_pr.md').write_text(SUITE_MD)
    tasks = [
        {'path': f'ocean/task{index}', 'status': 'pass', 'baseline': 'pass'}
        for index in range(3)
    ]
    (work_dir / 'omega_pr_results.json').write_text(
        json.dumps(
            {
                'complete': True,
                'summary': {
                    'total': 3,
                    'passed': 3,
                    'failed': 0,
                    'pending': 0,
                },
                'tasks': tasks,
            }
        )
    )
    build_dir = Path(state.pr_build_dir)
    (build_dir / 'ctest_output_for_pr.md').write_text(CTEST_MD)
    (build_dir / 'ctests.log').write_text(
        '100% tests passed, 0 tests failed out of 50\n'
    )
