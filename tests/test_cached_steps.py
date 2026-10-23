"""
Tests for how setup decides which steps get their outputs from the cache.

An explicit request (``--cached``, a suite's ``cached`` lines or
``--free_running``) wins over a task's ``free_running_steps``, which wins
over a step's ``default_cached``.  What setup reports as cached has to match
the steps it actually marked.
"""

import pytest

from polaris import Component, Step, Task
from polaris.setup import (
    _apply_free_running,
    _call_step_setup,
    _expand_and_mark_cached_steps,
    _skip_steps_feeding_only_cached,
)


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


def _make_chain(component, task, names, cached):
    """
    Add steps to a task, each linking the previous one's output as its
    input, and mark the last one cached or not
    """
    steps: list[Step] = []
    for name in names:
        step = Step(component=component, name=name, subdir=f'shared/{name}')
        step.add_output_file(f'{name}.nc')
        if steps:
            previous = steps[-1]
            step.add_input_file(
                filename='input.nc',
                work_dir_target=f'{previous.path}/{previous.name}.nc',
            )
        task.add_step(step)
        steps.append(step)
    steps[-1].cached = cached
    return steps


def _skip(tasks, work_dir):
    _call_step_setup(tasks, str(work_dir))
    return _skip_steps_feeding_only_cached(tasks)


def test_steps_feeding_only_a_cached_step_are_skipped(tmp_path):
    """
    A step that only makes inputs for a cached step has nothing to do, and
    neither does one that only feeds it in turn.
    """
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    _make_chain(component, task, ['prepare', 'weights', 'combine'], True)
    tasks = {task.path: task}

    skipped = _skip(tasks, tmp_path)

    assert skipped == {task.path: ['prepare', 'weights']}
    assert list(task.steps) == ['combine']
    assert task.steps_to_run == ['combine']
    assert task.config.get('task', 'steps_to_run') == 'combine'


def test_steps_feeding_a_step_that_runs_are_kept(tmp_path):
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    _make_chain(component, task, ['prepare', 'weights', 'combine'], False)
    tasks = {task.path: task}

    skipped = _skip(tasks, tmp_path)

    assert skipped == {task.path: []}
    assert list(task.steps) == ['prepare', 'weights', 'combine']


def test_a_step_used_by_a_step_that_runs_is_kept(tmp_path):
    """
    A step feeding a cached step and a step that runs is still needed, even
    when the step that runs is in another task.
    """
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    prepare, _ = _make_chain(component, task, ['prepare', 'combine'], True)
    other = Task(component=component, name='other')
    other.add_step(prepare)
    viz = Step(component=component, name='viz', indir=other.subdir)
    viz.add_input_file(
        filename='in.nc', target=f'../../{prepare.subdir}/prepare.nc'
    )
    other.add_step(viz)
    tasks = {task.path: task, other.path: other}

    skipped = _skip(tasks, tmp_path)

    assert skipped == {task.path: [], other.path: []}


def test_a_step_nothing_uses_is_kept(tmp_path):
    """A step at the end of the line is there for its own sake."""
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    _make_chain(component, task, ['combine'], True)
    task.add_step(Step(component=component, name='viz', indir=task.subdir))
    tasks = {task.path: task}

    skipped = _skip(tasks, tmp_path)

    assert skipped == {task.path: []}


@pytest.mark.parametrize('cached', [True, False])
def test_a_dependency_counts_as_a_use(tmp_path, cached):
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    prepare = Step(component=component, name='prepare', subdir='prepare')
    combine = Step(component=component, name='combine', subdir='combine')
    combine.add_output_file('combine.nc')
    combine.add_dependency(prepare)
    combine.cached = cached
    task.add_step(prepare)
    task.add_step(combine)
    tasks = {task.path: task}

    skipped = _skip(tasks, tmp_path)

    assert skipped == {task.path: ['prepare'] if cached else []}


def test_an_input_linked_through_another_input_is_followed(tmp_path):
    """
    A step may link a file that is itself a link in another step's work
    directory, and it is still the producer that it uses.
    """
    component = Component(name='e3sm/init')
    task = Task(component=component, name='task')
    mesh, relay = _make_chain(component, task, ['mesh', 'relay'], False)
    viz = Step(component=component, name='viz', indir=task.subdir)
    viz.add_input_file(
        filename='mesh.nc', work_dir_target=f'{relay.path}/input.nc'
    )
    task.add_step(viz)
    relay.cached = True
    tasks = {task.path: task}

    skipped = _skip(tasks, tmp_path)

    # viz runs and, through relay's link, uses what mesh makes
    assert skipped == {task.path: []}
