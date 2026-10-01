import dataclasses
import json
from pathlib import Path

import pr_test_report
import pr_test_results
import pr_test_setup
import pytest
from pr_test_fixtures import make_tester

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


@pytest.fixture
def finished(tmp_path, monkeypatch):
    """A row that setup prepared and whose jobs have finished"""
    fixture, manifest, _ = make_tester(tmp_path, monkeypatch)
    state = pr_test_setup.run_setup(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        polaris_dir=fixture.polaris_dir,
    )
    _finish(state)
    return fixture, manifest, state


def test_report(finished):
    fixture, manifest, state = finished

    text, url, path = pr_test_results.run_report(
        fixture.config, fixture.fork, manifest.branch, agent='Claude Code'
    )

    assert url is None
    assert text.startswith(
        '## Testing: chrysalis, oneapi-ifx, openmpi (Polaris `intel`)\n'
    )
    assert 'CTests: 50 of 50 passed. `omega_pr`: 3 of 3 tasks passed.' in text
    assert (
        f'Tested the merge of E3SM-Project/Omega#5 '
        f'(`{manifest.pr_head[:10]}`) into `develop` '
        f'(`{manifest.base_head[:10]}`) as `{manifest.test_commit[:10]}`, '
        f"against Polaris' Omega submodule "
        f'(`{manifest.baseline_commit[:10]}`).'
    ) in text
    # both files are pasted as they are
    assert SUITE_MD.strip() in text
    assert CTEST_MD.strip() in text
    assert 'No new warnings (0 in the PR build, 0 in the baseline build)' in (
        text
    )
    marker = pr_test_report.parse_marker(text)
    assert marker is not None
    assert marker['row'] == 'chrysalis/intel'
    assert (marker['status'], marker['result']) == ('complete', 'pass')
    assert marker['new_warnings'] == 0
    assert Path(path) == Path(state.pr_work_dir).parent / 'report.md'


def test_report_baseline_polaris(finished):
    _, manifest, _ = finished
    assert 'The baseline ran' not in pr_test_results.describe_commits(manifest)

    other = dataclasses.replace(manifest, baseline_polaris_commit='b' * 40)
    assert (
        f'The baseline ran with Polaris `bbbbbbbbbb`, without the changes '
        f'in Polaris `{manifest.polaris_commit[:10]}` that the PR needs.'
    ) in pr_test_results.describe_commits(other)


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

    text, _, _ = pr_test_results.run_report(
        fixture.config, fixture.fork, manifest.branch
    )

    assert (
        'CTests: 49 of 50 passed. `omega_pr`: 2 of 3 tasks passed, 1 with '
        'baseline differences.'
    ) in text
    marker = pr_test_report.parse_marker(text)
    assert marker is not None and marker['result'] == 'fail'


def test_report_before_the_jobs_finish(finished):
    fixture, manifest, state = finished
    Path(state.pr_work_dir, 'omega_pr_output_for_pr.md').unlink()

    with pytest.raises(pr_test_results.ReportError, match='not finished'):
        pr_test_results.run_report(
            fixture.config, fixture.fork, manifest.branch
        )


def test_report_not_run(finished):
    fixture, manifest, _ = finished

    text, _, path = pr_test_results.run_report(
        fixture.config,
        fixture.fork,
        manifest.branch,
        row_name='aurora/oneapi-ifx',
        not_run='Aurora is down for maintenance.',
    )

    assert text.startswith('## Testing: aurora, oneapi-ifx, mpich\n')
    assert 'Not run: Aurora is down for maintenance.' in text
    marker = pr_test_report.parse_marker(text)
    assert marker is not None
    assert (marker['row'], marker['status']) == (
        'aurora/oneapi-ifx',
        'not-run',
    )
    assert Path(path).parent.name == 'aurora_oneapi-ifx'


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
