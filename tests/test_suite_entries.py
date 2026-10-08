import importlib.resources as imp_res

import pytest

from polaris.tasks import get_components

SUITE_PACKAGES = [
    'polaris.suites.ocean',
    'polaris.suites.mesh',
    'polaris.suites.seaice',
    'polaris.suites.e3sm.init',
]


def _all_task_paths():
    """Every task path Polaris registers, across all components."""
    return {
        task.path
        for component in get_components()
        for task in component.tasks.values()
    }


def _suite_files():
    """Every suite file, as (package, filename) pairs."""
    suites = []
    for package in SUITE_PACKAGES:
        try:
            files = imp_res.files(package)
        except ModuleNotFoundError:
            continue
        for resource in files.iterdir():
            if resource.is_file() and resource.name.endswith('.txt'):
                suites.append((package, resource.name))
    return sorted(suites)


def _entries(package, filename):
    """The task paths a suite file lists, ignoring blanks and comments."""
    text = imp_res.files(package).joinpath(filename).read_text()
    entries = []
    for line in text.splitlines():
        line = line.strip()
        # blank lines and comments carry nothing, and a 'cached:' line names
        # steps of the task above it rather than a task of its own
        if not line or line.startswith('#') or line.startswith('cached:'):
            continue
        entries.append(line)
    return entries


@pytest.mark.parametrize('package, filename', _suite_files())
def test_suite_entries_name_real_tasks(package, filename):
    """
    Every task a suite lists actually exists.

    A suite entry is a path string with nothing checking it, so a task that
    is renamed or removed leaves the suite naming something that is gone --
    and a new entry with a typo, or missing the trailing ``/task`` that a task
    subdirectory ends in, is equally silent.  Either way the suite quietly
    stops covering what it claims to.
    """
    task_paths = _all_task_paths()
    missing = [
        entry
        for entry in _entries(package, filename)
        if entry not in task_paths
    ]
    assert not missing, (
        f'{filename} lists tasks that do not exist: {sorted(missing)}'
    )


@pytest.mark.parametrize('package, filename', _suite_files())
def test_suite_entries_are_unique(package, filename):
    """A task listed twice in one suite would just be set up twice."""
    entries = _entries(package, filename)
    duplicates = {entry for entry in entries if entries.count(entry) > 1}
    assert not duplicates, (
        f'{filename} lists tasks more than once: {sorted(duplicates)}'
    )
