"""
Tests for leaving out tasks that say in configure() that they do not apply.
"""

import pytest

from polaris import Component, Task
from polaris.setup import _drop_skipped_tasks


def _tasks(*names):
    component = Component(name='ocean')
    return {
        f'ocean/{name}': Task(component=component, name=name) for name in names
    }


def test_a_task_with_a_skip_reason_is_left_out(capsys):
    tasks = _tasks('kept', 'skipped')
    tasks['ocean/skipped'].skip_reason = 'not on this machine'

    _drop_skipped_tasks(tasks)

    assert list(tasks) == ['ocean/kept']
    assert 'ocean/skipped: not on this machine' in capsys.readouterr().out


def test_setting_up_only_skipped_tasks_is_an_error():
    tasks = _tasks('skipped')
    tasks['ocean/skipped'].skip_reason = 'not on this machine'

    with pytest.raises(ValueError, match='None of the requested tasks'):
        _drop_skipped_tasks(tasks)
