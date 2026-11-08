import json

import pr_test_report as report
from pr_test_rows import Row


def test_summarize_suite_without_baseline(tmp_path):
    pr_dir = _write_results(
        tmp_path / 'pr',
        [_task('a'), _task('b', baseline='fail', diffs={'temp': 1e-3})],
    )

    passed, cell = report.summarize_suite(str(pr_dir), 'omega_pr')

    assert not passed
    assert cell == '1 of 2 passed, 1 with baseline differences'


def test_summarize_suite_task_failed_in_baseline(tmp_path):
    baseline_dir = _write_results(
        tmp_path / 'baseline', [_task('a'), _task('b', execution='fail')]
    )
    # a missing baseline file gives a failed comparison with no norms
    pr_dir = _write_results(
        tmp_path / 'pr', [_task('a'), _task('b', baseline='fail')]
    )

    passed, cell = report.summarize_suite(
        str(pr_dir), 'omega_pr', str(baseline_dir)
    )

    assert passed
    assert cell == (
        '2 of 2 passed, 1 task failed in the baseline (1 not compared)'
    )


def test_summarize_suite_differs_before_baseline_failed(tmp_path):
    # a step that ran in the baseline before the task failed can differ
    baseline_dir = _write_results(
        tmp_path / 'baseline', [_task('a', execution='fail')]
    )
    pr_dir = _write_results(
        tmp_path / 'pr', [_task('a', baseline='fail', diffs={'temp': 1e-3})]
    )

    passed, cell = report.summarize_suite(
        str(pr_dir), 'omega_pr', str(baseline_dir)
    )

    assert not passed
    assert cell == (
        '0 of 1 passed, 1 with baseline differences, 1 task failed in the '
        'baseline'
    )


def test_summarize_suite_task_failed_in_both(tmp_path):
    baseline_dir = _write_results(
        tmp_path / 'baseline', [_task('a', execution='fail'), _task('b')]
    )
    pr_dir = _write_results(
        tmp_path / 'pr', [_task('a', execution='fail'), _task('b')]
    )

    passed, cell = report.summarize_suite(
        str(pr_dir), 'omega_pr', str(baseline_dir)
    )

    assert not passed
    assert cell == '1 of 2 passed, 1 task failed in the baseline'


def _task(path, execution='pass', baseline='pass', diffs=None):
    norms = {
        variable: {'l1': value, 'l2': value, 'linf': value}
        for variable, value in (diffs or {}).items()
    }
    return {
        'path': path,
        'execution': execution,
        'baseline': baseline if execution == 'pass' else None,
        'baseline_diffs': norms,
    }


def _write_results(work_dir, tasks):
    work_dir.mkdir()
    contents = {'suite': 'omega_pr', 'complete': True, 'tasks': tasks}
    (work_dir / 'omega_pr_results.json').write_text(
        json.dumps(contents), encoding='utf-8'
    )
    return work_dir


def test_compare_with_baseline_task_failed_in_baseline(tmp_path):
    baseline_dir = _write_results(
        tmp_path / 'baseline',
        [_task('a'), _task('b', execution='fail'), _task('c')],
    )
    pr_dir = _write_results(
        tmp_path / 'pr',
        [
            _task('a'),
            _task('b', baseline='fail'),
            _task('c', baseline='fail', diffs={'temp': 1e-3}),
        ],
    )

    comparison = report.compare_with_baseline(
        str(pr_dir), 'omega_pr', str(baseline_dir)
    )

    assert comparison.bit_for_bit == ['a']
    assert comparison.differ == {'c': ['temp']}
    assert comparison.failed_in_baseline == ['b']


def test_format_bit_for_bit_names_each_task_once():
    mpaso = Row('chrysalis', 'gnu', 'openmpi', model='mpas-ocean')
    omega_gnu = Row('chrysalis', 'gnu', 'openmpi', model='omega')
    omega_intel = Row('chrysalis', 'intel', 'openmpi', model='omega')
    skipped = Row('chrysalis', 'oneapi', 'openmpi', model='omega')
    mesh = {'mesh/a': ['xCell', 'yCell'], 'mesh/b': ['xCell']}
    rows = [
        (
            mpaso,
            report.BaselineComparison(
                'mpaso_pr', differ={**mesh, 'overflow': ['temperature']}
            ),
            '',
        ),
        (
            omega_gnu,
            report.BaselineComparison(
                'omega_pr', differ={**mesh, 'qu240': ['salinity']}
            ),
            '',
        ),
        (
            omega_intel,
            report.BaselineComparison(
                'omega_pr', differ={**mesh, 'qu240': ['salinity']}
            ),
            '',
        ),
        (skipped, None, 'it was not run: the queue is down'),
    ]

    text = report.format_bit_for_bit(rows)

    assert '**4 tasks differ from the baseline:**\n\n' in text
    assert '- `mesh/a`, `mesh/b`: on every row compared\n' in text
    assert '- `overflow`: on chrysalis, gnu, openmpi (MPAS-Ocean)\n' in text
    assert '- `qu240`: on every Omega row compared\n' in text
    assert (
        '1 row was not compared:\n\n- chrysalis, oneapi, openmpi (Omega), '
        'because it was not run: the queue is down.'
    ) in text
    assert 'xCell' not in text
    assert text.count('mesh/a') == 1


def test_format_bit_for_bit_rows_not_compared_share_a_reason():
    gnu = Row('pm-cpu', 'gnu', 'mpich', model='omega')
    intel = Row('pm-cpu', 'intel', 'mpich', model='omega')
    gpu = Row('pm-gpu', 'gnugpu', 'mpich', model='omega')
    reason = 'it was not run: no node hours'
    rows = [
        (gnu, None, reason),
        (intel, None, reason),
        (gpu, report.BaselineComparison('omega_pr', bit_for_bit=['a']), ''),
    ]

    text = report.format_bit_for_bit(rows)

    assert (
        '2 rows were not compared:\n\n- pm-cpu, gnu, mpich (Omega); pm-cpu, '
        'intel, mpich (Omega), because it was not run: no node hours.'
    ) in text
    assert text.count(reason) == 1
