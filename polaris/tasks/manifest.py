"""
The task manifest: every task's path, steps and task group, without
building any tasks

Building every task imports most of Polaris, so ``polaris list`` reads the
tasks from a JSON file instead, and ``polaris setup`` reads from it which
task groups to build.  The file is ``task_manifest.json`` in the ``polaris``
package directory, which for a development installation is the ``polaris``
directory of the branch.  It records a key computed from the path,
modification time and size of every ``.py``, ``.cfg`` and ``.yaml`` file in
the package, and is rebuilt whenever the key no longer matches, so it is
never stale.  If it can't be written, as in a read-only installation, the
rebuilt manifest is used without being saved.
"""

import hashlib
import json
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

# change this when the manifest's contents change, so old ones are rebuilt
MANIFEST_FORMAT = 1

MANIFEST_FILENAME = 'task_manifest.json'

_KEY_SUFFIXES = ('.py', '.cfg', '.yaml')

# the polaris package, the parent of polaris/tasks
_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_manifest(
    package_dir: str = _PACKAGE_DIR,
    build: Optional[Callable[[], List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    The tasks in the manifest, rebuilding it if it is stale

    Parameters
    ----------
    package_dir : str, optional
        The directory of the ``polaris`` package

    build : callable, optional
        A function that builds the task entries; by default,
        :py:func:`build_task_entries`

    Returns
    -------
    tasks : list of dict
        One entry per task, in the order ``polaris list`` numbers them, with
        keys ``path``, ``name``, ``component``, ``subdir``, ``task_group``,
        the ``[component, task group]`` that adds the task, and ``steps``,
        a list of ``[name, path]`` pairs
    """
    key = compute_key(package_dir)
    filename = os.path.join(package_dir, MANIFEST_FILENAME)
    manifest = _read(filename)
    if manifest is not None and manifest.get('key') == key:
        return manifest['tasks']

    if build is None:
        build = build_task_entries
    tasks = build()
    _write(filename, {'key': key, 'tasks': tasks})
    return tasks


def compute_key(package_dir: str = _PACKAGE_DIR) -> str:
    """
    A key that changes whenever a file that could define a task changes

    Parameters
    ----------
    package_dir : str, optional
        The directory of the ``polaris`` package

    Returns
    -------
    key : str
        A SHA-256 hex digest of the manifest format and the relative path,
        modification time and size of every ``.py``, ``.cfg`` and ``.yaml``
        file under ``package_dir``
    """
    entries: List[str] = []
    _collect(package_dir, '', entries)
    entries.sort()
    digest = hashlib.sha256(f'format {MANIFEST_FORMAT}\n'.encode())
    for entry in entries:
        digest.update(entry.encode())
    return digest.hexdigest()


def build_task_entries() -> List[Dict[str, Any]]:
    """
    Build every task and describe it

    Returns
    -------
    tasks : list of dict
        The manifest's entries, as returned by :py:func:`get_manifest`
    """
    # deferred because building every task is what the manifest is there to
    # avoid, and only a stale manifest needs it
    from polaris.tasks import (
        add_task_groups,
        get_components,
        get_task_group_names,
    )

    components = get_components(add_tasks=False)

    # add the task groups one at a time to find out which task group adds
    # each task; a task group may add tasks to another component
    groups: Dict[str, Tuple[str, str]] = {}
    for component in components:
        for group in get_task_group_names(component.name):
            add_task_groups(component, [group])
            for other in components:
                for task in other.tasks.values():
                    groups.setdefault(task.path, (component.name, group))

    # list the tasks in the order polaris list has always numbered them
    tasks = []
    for component in components:
        for task in component.tasks.values():
            group_component, group = groups[task.path]
            tasks.append(_describe(task, group_component, group))
    return tasks


def _describe(task, group_component: str, group: str) -> Dict[str, Any]:
    return {
        'path': task.path,
        'name': task.name,
        'component': task.component.name,
        'subdir': task.subdir,
        'task_group': [group_component, group],
        'steps': [[step.name, step.path] for step in task.steps.values()],
    }


def _collect(directory: str, relative: str, entries: List[str]) -> None:
    """
    Add an entry for each relevant file under a directory

    ``os.scandir`` gets the size and modification time from the directory
    listing on most file systems, which is many times faster than calling
    ``os.stat`` on each file.
    """
    with os.scandir(directory) as it:
        for entry in it:
            if entry.is_dir(follow_symlinks=False):
                if entry.name == '__pycache__':
                    continue
                _collect(
                    entry.path, os.path.join(relative, entry.name), entries
                )
            elif entry.name.endswith(_KEY_SUFFIXES):
                stat = entry.stat()
                entries.append(
                    f'{os.path.join(relative, entry.name)} '
                    f'{stat.st_mtime_ns} {stat.st_size}\n'
                )


def _read(filename: str) -> Optional[Dict[str, Any]]:
    try:
        with open(filename) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(filename: str, manifest: Dict[str, Any]) -> None:
    """
    Write the manifest atomically, or not at all if the directory is
    read-only, so that concurrent ``polaris`` commands never read a partial
    file
    """
    directory = os.path.dirname(filename)
    try:
        fd, tmp_filename = tempfile.mkstemp(
            dir=directory, prefix='.task_manifest.', suffix='.tmp'
        )
    except OSError:
        return
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(manifest, f, separators=(',', ':'))
            f.write('\n')
        # mkstemp() makes the file readable only by its owner
        os.chmod(tmp_filename, 0o666 & ~_get_umask())
        os.replace(tmp_filename, filename)
    except OSError:
        try:
            os.remove(tmp_filename)
        except OSError:
            pass


def _get_umask() -> int:
    umask = os.umask(0)
    os.umask(umask)
    return umask
