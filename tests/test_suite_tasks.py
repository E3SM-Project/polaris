import importlib.resources as imp_res
from pathlib import Path

import pytest

import polaris.tasks
from polaris.suite import _parse_suite
from polaris.tasks import get_components


def _get_suite_files():
    """Find every suite file under ``polaris.suites``."""
    suites_dir = Path(str(imp_res.files('polaris.suites')))
    return sorted(
        str(path.relative_to(suites_dir)) for path in suites_dir.rglob('*.txt')
    )


@pytest.fixture(scope='module')
def task_paths():
    """The paths of all registered tasks, without leaking them to tests."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(polaris.tasks, '_tasks_added', False)
        _clear_components()
        paths = {
            task.path
            for component in get_components()
            for task in component.tasks.values()
        }
        _clear_components()
    return paths


@pytest.mark.parametrize('suite_file', _get_suite_files())
def test_suite_tasks_are_registered(suite_file, task_paths):
    """
    Every task a suite names must exist, or the suite fails to set up.

    A suite entry is a path string with nothing else checking it, so a task
    that is renamed or removed, or an entry with a typo or without the
    trailing ``/task`` a task subdirectory ends in, leaves the suite naming
    something that is not there.
    """
    tasks = _suite_tasks(suite_file)

    assert len(tasks) > 0
    missing = [task for task in tasks if task not in task_paths]
    assert missing == []


@pytest.mark.parametrize('suite_file', _get_suite_files())
def test_suite_tasks_are_unique(suite_file):
    """A task listed twice in one suite would just be set up twice."""
    tasks = _suite_tasks(suite_file)

    duplicates = sorted({task for task in tasks if tasks.count(task) > 1})
    assert duplicates == []


def _suite_tasks(suite_file):
    """The tasks a suite file names, as ``polaris suite`` reads them."""
    text = imp_res.files('polaris.suites').joinpath(suite_file).read_text()
    tasks, _ = _parse_suite(text)
    return tasks


def _clear_components():
    for component in get_components(add_tasks=False):
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
