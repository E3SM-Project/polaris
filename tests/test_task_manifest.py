import json
import os
import stat

from polaris.tasks.manifest import (
    MANIFEST_FILENAME,
    compute_key,
    get_manifest,
)


def test_key_changes_when_a_task_module_is_touched(tmp_path):
    package = _make_package(tmp_path)
    key = compute_key(str(package))

    module = package / 'tasks' / 'ocean' / 'task.py'
    stat_result = module.stat()
    os.utime(
        module, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 10**9)
    )

    assert compute_key(str(package)) != key


def test_key_ignores_other_files(tmp_path):
    package = _make_package(tmp_path)
    key = compute_key(str(package))

    (package / 'notes.txt').write_text('not part of any task')
    (package / 'tasks' / '__pycache__' / 'task.cpython-314.pyc').write_text(
        'compiled'
    )

    assert compute_key(str(package)) == key


def test_stale_manifest_is_rebuilt_and_fresh_one_is_read(tmp_path):
    package = _make_package(tmp_path)
    build = _CountingBuild()

    first = get_manifest(str(package), build=build)
    second = get_manifest(str(package), build=build)
    assert build.count == 1
    assert first == second == [{'path': 'ocean/task1'}]

    module = package / 'tasks' / 'ocean' / 'task.py'
    module.write_text('# a new task\n')
    third = get_manifest(str(package), build=build)
    assert build.count == 2
    assert third == [{'path': 'ocean/task2'}]

    with open(package / MANIFEST_FILENAME) as f:
        assert json.load(f)['tasks'] == third


def test_read_only_package_still_gets_a_manifest(tmp_path):
    package = _make_package(tmp_path)
    mode = package.stat().st_mode
    os.chmod(package, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        tasks = get_manifest(str(package), build=lambda: [{'path': 'a'}])
    finally:
        os.chmod(package, mode)

    assert tasks == [{'path': 'a'}]
    assert not (package / MANIFEST_FILENAME).exists()


class _CountingBuild:
    """A stand-in for building the tasks that counts how often it is used"""

    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return [{'path': f'ocean/task{self.count}'}]


def _make_package(tmp_path):
    package = tmp_path / 'polaris'
    (package / 'tasks' / 'ocean').mkdir(parents=True)
    (package / 'tasks' / '__pycache__').mkdir()
    (package / '__init__.py').write_text('')
    (package / 'default.cfg').write_text('[section]\n')
    (package / 'tasks' / 'ocean' / 'task.py').write_text('# a task\n')
    (package / 'tasks' / 'ocean' / 'task.yaml').write_text('a: 1\n')
    return package
