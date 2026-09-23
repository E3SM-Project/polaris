"""
Tests for how setup decides which steps get their outputs from the cache.

An explicit request (``--cached``, a suite's ``cached`` lines or
``--free_running``) wins over a task's ``free_running_steps``, which wins
over a step's ``default_cached``.  What setup reports as cached has to match
the steps it actually marked.
"""

import pytest

from polaris import Component, Step, Task
from polaris.setup import _apply_free_running, _expand_and_mark_cached_steps


def _make_task(component, name='task', free_running=False):
    """Build a task with an expensive shared step and a viz step."""
    task = Task(component=component, name=name)
    expensive = Step(component=component, name='expensive', subdir='shared')
    expensive.default_cached = True
    task.add_step(expensive)
    task.add_step(Step(component=component, name='viz', indir=task.subdir))
    if free_running:
        for step in task.steps.values():
            task.free_running_steps.add(step.subdir)
    return task


def test_default_cached_step_is_cached():
    task = _make_task(Component(name='ocean'))
    cached_steps: dict[str, list[str]] = {task.path: []}

    _expand_and_mark_cached_steps({task.path: task}, cached_steps)

    assert task.steps['expensive'].cached
    assert not task.steps['viz'].cached
    assert cached_steps[task.path] == ['expensive']


def test_free_running_task_overrides_default_cached():
    task = _make_task(Component(name='ocean'), free_running=True)
    cached_steps: dict[str, list[str]] = {task.path: []}

    _expand_and_mark_cached_steps({task.path: task}, cached_steps)

    assert not task.steps['expensive'].cached
    assert cached_steps[task.path] == []


def test_explicit_cached_overrides_free_running_task():
    task = _make_task(Component(name='ocean'), free_running=True)
    cached_steps = {task.path: ['expensive']}

    _expand_and_mark_cached_steps({task.path: task}, cached_steps)

    assert task.steps['expensive'].cached
    assert not task.steps['viz'].cached
    assert cached_steps[task.path] == ['expensive']


def test_explicit_cached_in_one_task_overrides_another_free_running():
    """
    A shared step is one object, so a suite that caches it in one task
    caches it in a task that would otherwise run it free, too.
    """
    component = Component(name='ocean')
    owner = _make_task(component, name='owner', free_running=True)
    user = Task(component=component, name='user')
    user.add_step(owner.steps['expensive'])
    tasks = {owner.path: owner, user.path: user}
    cached_steps = {owner.path: [], user.path: ['expensive']}

    _expand_and_mark_cached_steps(tasks, cached_steps)

    assert owner.steps['expensive'].cached
    assert cached_steps[owner.path] == ['expensive']
    assert cached_steps[user.path] == ['expensive']


def test_cli_free_running_overrides_default_cached():
    task = _make_task(Component(name='ocean'))
    tasks = {task.path: task}
    cached_steps: dict[str, list[str]] = {task.path: []}

    _apply_free_running(tasks, [['expensive']], cached_steps)
    _expand_and_mark_cached_steps(tasks, cached_steps)

    assert not task.steps['expensive'].cached
    assert cached_steps[task.path] == []


@pytest.mark.parametrize('cached', [['expensive'], ['_all']])
def test_cached_and_free_running_conflict(cached):
    task = _make_task(Component(name='ocean'))
    cached_steps = {task.path: cached}

    with pytest.raises(ValueError, match='both --cached and --free_running'):
        _apply_free_running({task.path: task}, [['expensive']], cached_steps)


def test_cached_step_without_outputs_is_refused():
    component = Component(name='ocean')
    step = Step(component=component, name='viz')
    step.cached = True

    with pytest.raises(ValueError, match='has no output files'):
        step.process_inputs_and_outputs()


def test_cached_step_output_must_be_in_cache_database():
    component = Component(name='ocean')
    step = Step(component=component, name='expensive')
    step.add_output_file('output.nc')
    step.cached = True

    with pytest.raises(ValueError, match='has not been added'):
        step.process_inputs_and_outputs()
