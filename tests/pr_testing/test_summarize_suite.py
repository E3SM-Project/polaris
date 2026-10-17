import json

import pr_test_report as report


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
