import json

import cdash


def _write_results(suite_dir, tasks):
    (suite_dir / 'omega_nightly_results.json').write_text(
        json.dumps({'tasks': tasks})
    )


def test_task_results_from_parallel_step_logs(tmp_path):
    _write_results(
        tmp_path,
        [
            {
                'path': 'ocean/a/default',
                'status': 'pass',
                'log': None,
                'steps_to_run': ['mesh', 'forward'],
            },
            {
                'path': 'ocean/b/default',
                'status': 'fail',
                'log': None,
                'steps_to_run': ['forward', 'analysis'],
            },
        ],
    )
    outputs = tmp_path / 'case_outputs'
    outputs.mkdir()
    (outputs / 'ocean_shared_mesh.log').write_text('\x1b[32mmesh\x1b[0m\n')
    (outputs / 'ocean_a_default_forward.log').write_text('a forward\n')
    (outputs / 'ocean_b_default_forward.log').write_text('b forward\n')
    step_paths = {
        'ocean/a/default': {
            # a shared step, whose path is not under its task's
            'mesh': 'ocean/shared/mesh',
            'forward': 'ocean/a/default/forward',
        },
        'ocean/b/default': {
            'forward': 'ocean/b/default/forward',
            'analysis': 'ocean/b/default/analysis',
        },
    }

    results = cdash.task_results(str(tmp_path), 'omega_nightly', step_paths)

    assert [result['name'] for result in results] == [
        'ocean_a_default',
        'ocean_b_default',
    ]
    assert [result['passed'] for result in results] == [True, False]
    assert results[0]['output'] == (
        '==> case_outputs/ocean_shared_mesh.log <==\nmesh\n\n'
        '==> case_outputs/ocean_a_default_forward.log <==\na forward\n'
    )
    # a step that a failed step kept from running left no log
    assert (
        'case_outputs/ocean_b_default_analysis.log was not written'
        in results[1]['output']
    )


def test_task_results_from_serial_task_log(tmp_path):
    _write_results(
        tmp_path,
        [
            {
                'path': 'ocean/a/default',
                'status': 'pass',
                'log': 'case_outputs/ocean_a_default.log',
                'steps_to_run': None,
            }
        ],
    )
    outputs = tmp_path / 'case_outputs'
    outputs.mkdir()
    (outputs / 'ocean_a_default.log').write_text('POLARIS TASK: PASS\n')

    results = cdash.task_results(str(tmp_path), 'omega_nightly', {})

    assert results == [
        {
            'name': 'ocean_a_default',
            'passed': True,
            'output': 'POLARIS TASK: PASS\n',
        }
    ]


def test_task_results_without_results_file(tmp_path):
    assert cdash.task_results(str(tmp_path), 'omega_nightly', {}) == []
