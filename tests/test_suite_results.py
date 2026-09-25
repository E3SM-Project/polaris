import json
import math
import os
from types import SimpleNamespace

import mpas_tools.io
import numpy as np
import pytest

import polaris.run.serial as serial
from polaris.run.results import SCHEMA_VERSION, TaskResult
from polaris.version import __version__

PROVENANCE = """\
***********************************************************************
polaris git version: 1.1.0-alpha.6-12-gabc1234

command: polaris suite -c ocean -t omega_pr

machine: chrysalis

partition: compute

compiler: intel

work directory: {work_dir}

build directory: /path/to/build

build type: Release

tasks:
  path:          ocean/pass
***********************************************************************
"""


class _FakeConfig:
    """Just enough of a config parser for ``_log_and_run_task()``"""

    def get(self, section, option):
        if option == 'steps_to_run':
            return 'init forward'
        return 'NETCDF3_64BIT'


class _FakeRunTask:
    """
    A stand-in for ``_run_task()`` whose outcome depends on the task's path,
    and which records what the results file said while each task ran
    """

    def __init__(self, results_filename):
        self.results_filename = results_filename
        self.snapshots = {}

    def __call__(self, task, available_resources):
        with open(self.results_filename) as handle:
            self.snapshots[task.path] = json.load(handle)
        if task.path.endswith('error'):
            raise RuntimeError('step failed')
        if task.path.endswith('diff'):
            diffs = {
                'temperature': {
                    'l1': np.float32(0.5),
                    'l2': np.float64(0.25),
                    'linf': np.float32(0.125),
                },
                'salinity': {'l1': math.nan, 'l2': math.inf, 'linf': 0.0},
            }
            return False, diffs
        return None, {}


def _set_up(tmp_path, monkeypatch, paths, name='omega_pr', is_task=False):
    """
    Set up a suite of fake tasks without a pickle file, with
    ``_run_task()`` mocked
    """
    work_dir = str(tmp_path)
    with open(os.path.join(work_dir, 'provenance'), 'w') as handle:
        handle.write(PROVENANCE.format(work_dir=work_dir))

    component = SimpleNamespace(
        name='ocean', get_available_resources=lambda: {}
    )
    tasks = {}
    for path in paths:
        task_dir = os.path.join(work_dir, path)
        os.makedirs(task_dir)
        tasks[path] = SimpleNamespace(
            path=path,
            name=os.path.basename(path),
            work_dir=task_dir,
            base_work_dir=work_dir,
            component=component,
            config=SimpleNamespace(filepath='task.cfg'),
            steps={'init': None, 'forward': None},
        )
    suite_work_dir = tasks[paths[0]].work_dir if is_task else work_dir
    suite = {'name': name, 'tasks': tasks, 'work_dir': suite_work_dir}

    fake_run_task = _FakeRunTask(
        os.path.join(suite_work_dir, f'{name}_results.json')
    )

    monkeypatch.chdir(suite_work_dir)
    monkeypatch.delenv('SLURM_JOB_ID', raising=False)
    monkeypatch.setattr(serial, 'unpickle_suite', lambda suite_name: suite)
    monkeypatch.setattr(serial, 'setup_config', lambda *args: _FakeConfig())
    monkeypatch.setattr(serial, 'set_parallel_systems', lambda *args: None)
    monkeypatch.setattr(serial, '_run_task', fake_run_task)
    monkeypatch.setattr(serial, 'log_function_call', lambda **kwargs: None)
    # _log_and_run_task() sets these module-wide defaults
    monkeypatch.setattr(mpas_tools.io, 'default_format', 'NETCDF4')
    monkeypatch.setattr(mpas_tools.io, 'default_engine', None)

    return suite_work_dir, fake_run_task.snapshots


def _read_results(work_dir, name):
    with open(os.path.join(work_dir, f'{name}_results.json')) as handle:
        # parse_constant raises if the file is not strict JSON
        return json.load(handle, parse_constant=_reject_constant)


def _reject_constant(name):
    raise ValueError(f'{name} is not valid JSON')


def test_results_file_records_each_outcome(tmp_path, monkeypatch):
    paths = ['ocean/pass', 'ocean/error', 'ocean/diff']
    work_dir, _ = _set_up(tmp_path, monkeypatch, paths)

    with pytest.raises(SystemExit):
        serial.run_tasks('omega_pr')

    results = _read_results(work_dir, 'omega_pr')
    assert results['schema_version'] == SCHEMA_VERSION
    assert results['suite'] == 'omega_pr'
    assert results['complete'] is True
    assert results['elapsed_seconds'] >= 0.0
    assert results['summary'] == {
        'total': 3,
        'passed': 1,
        'failed': 2,
        'pending': 0,
    }

    provenance = results['provenance']
    assert provenance['polaris_version'] == __version__
    assert provenance['polaris_git_version'] == '1.1.0-alpha.6-12-gabc1234'
    assert provenance['machine'] == 'chrysalis'
    assert provenance['partition'] == 'compute'
    assert provenance['compiler'] == 'intel'
    assert provenance['build_type'] == 'Release'
    assert provenance['component_git_version'] is None
    assert provenance['baseline_work_directory'] is None

    tasks = {task['path']: task for task in results['tasks']}
    assert list(tasks) == paths

    passed = tasks['ocean/pass']
    assert passed['status'] == 'pass'
    assert passed['execution'] == 'pass'
    assert passed['baseline'] is None
    assert passed['steps_to_run'] == ['init', 'forward']
    assert passed['log'] == 'case_outputs/ocean_pass.log'
    assert os.path.exists(os.path.join(work_dir, passed['log']))
    assert passed['baseline_diffs'] == {}

    error = tasks['ocean/error']
    assert error['status'] == 'fail'
    assert error['execution'] == 'fail'
    assert error['baseline'] is None

    diff = tasks['ocean/diff']
    assert diff['status'] == 'fail'
    assert diff['execution'] == 'pass'
    assert diff['baseline'] == 'fail'
    assert diff['baseline_diffs'] == {
        'temperature': {'l1': 0.5, 'l2': 0.25, 'linf': 0.125},
        'salinity': {'l1': 'NaN', 'l2': 'Infinity', 'linf': 0.0},
    }

    for task in results['tasks']:
        assert task['elapsed_seconds'] >= 0.0

    # the text outputs are still written
    assert os.path.exists(os.path.join(work_dir, 'omega_pr_output_for_pr.md'))
    with open(os.path.join(work_dir, 'case_outputs/ocean_diff.log')) as log:
        assert 'POLARIS BASELINE: FAIL' in log.read()


def test_results_file_is_written_before_each_task(tmp_path, monkeypatch):
    paths = ['ocean/first', 'ocean/second', 'ocean/third']
    work_dir, snapshots = _set_up(tmp_path, monkeypatch, paths)

    serial.run_tasks('omega_pr')

    first = snapshots['ocean/first']
    assert first['complete'] is False
    assert [task['status'] for task in first['tasks']] == ['pending'] * 3
    assert first['summary']['pending'] == 3

    second = snapshots['ocean/second']
    assert second['complete'] is False
    assert [task['status'] for task in second['tasks']] == [
        'pass',
        'pending',
        'pending',
    ]
    pending = second['tasks'][1]
    assert pending['execution'] is None
    assert pending['elapsed_seconds'] is None
    assert pending['steps_to_run'] is None

    results = _read_results(work_dir, 'omega_pr')
    assert results['complete'] is True
    assert results['summary']['passed'] == 3
    assert not os.path.exists(
        os.path.join(work_dir, 'omega_pr_results.json.tmp')
    )


def test_single_task_writes_task_results(tmp_path, monkeypatch):
    work_dir, _ = _set_up(
        tmp_path, monkeypatch, ['ocean/pass'], name='task', is_task=True
    )

    serial.run_tasks('task', is_task=True)

    results = _read_results(work_dir, 'task')
    assert results['complete'] is True
    assert results['suite'] == 'task'
    # provenance comes from the base work directory
    assert results['provenance']['machine'] == 'chrysalis'
    (task,) = results['tasks']
    assert task['status'] == 'pass'
    assert task['log'] is None


def test_task_result_status():
    assert TaskResult(path='a').status == 'pending'
    assert TaskResult(path='a', execution_passed=True).status == 'pass'
    assert TaskResult(path='a', execution_passed=False).status == 'fail'
    result = TaskResult(path='a', execution_passed=True, baseline_passed=True)
    assert result.status == 'pass'
    result.baseline_passed = False
    assert result.status == 'fail'
