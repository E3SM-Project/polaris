"""
Tests for how a step picks up what its dependencies did when they ran.

``polaris serial`` pickles a step that others depend on once it has run, and
loads that pickle before running each step that depends on it.  Many steps
refer to a dependency both through ``dependencies`` and directly, as an
attribute, so loading has to leave both pointing at one object or each
pickle along a chain of dependencies holds the one before it twice.
"""

import gc
import os
import pickle
from collections import Counter

from polaris import Component, Step, Task
from polaris.run import complete_step_run, load_dependencies


class _Chained(Step):
    """
    A step that refers to the step before it directly, as well as through
    ``dependencies``.
    """

    def __init__(self, component, name, previous=None):
        super().__init__(component=component, name=name)
        self.previous = previous
        self.result = None
        if previous is not None:
            self.add_dependency(previous, name='previous')


def _make_chain(work_dir, length):
    """Build a task whose steps each depend on the one before."""
    component = Component(name='ocean')
    task = Task(component=component, name='task')
    steps = []
    previous = None
    for index in range(length):
        step = _Chained(component, f'step_{index}', previous=previous)
        step.work_dir = os.path.join(work_dir, step.name)
        os.makedirs(step.work_dir)
        task.add_step(step)
        steps.append(step)
        previous = step
    component.add_task(task)
    return steps


def _run_chain(steps):
    """Load each step's dependencies and pickle it, as a serial run does."""
    for step in steps:
        os.chdir(step.work_dir)
        load_dependencies(step)
        step.result = f'{step.name} ran'
        complete_step_run(step)


def _count_steps(root):
    """Count the Step objects reachable from ``root`` for each path."""
    seen = set()
    stack = [root]
    counts: Counter[str] = Counter()
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, Step):
            counts[obj.path] += 1
        if isinstance(obj, (str, bytes, int, float)):
            continue
        stack.extend(gc.get_referents(obj))
    return counts


def test_a_pickle_holds_each_step_of_its_chain_once(tmp_path, monkeypatch):
    """
    Replacing a dependency with its unpickled copy left the step referring
    to the copy through ``dependencies`` and to the original directly, so
    each pickle held the one before it twice.
    """
    monkeypatch.chdir(tmp_path)
    steps = _make_chain(str(tmp_path), length=6)

    _run_chain(steps[:-1])

    with open(
        os.path.join(steps[-2].work_dir, 'step_after_run.pickle'), 'rb'
    ) as handle:
        unpickled = pickle.load(handle)
    counts = _count_steps(unpickled)
    assert counts['ocean/step_0'] == 1
    assert max(counts.values()) == 1


def test_a_dependency_is_updated_in_place(tmp_path, monkeypatch):
    """
    What a dependency did when it ran is seen through ``dependencies`` and
    through the step's own reference to it, which are the same object.
    """
    monkeypatch.chdir(tmp_path)
    first, second = _make_chain(str(tmp_path), length=2)
    os.chdir(first.work_dir)
    first.result = 'first ran'
    complete_step_run(first)
    # the dependency ran in another process, so this one never saw it run
    first.result = None

    os.chdir(second.work_dir)
    load_dependencies(second)

    assert second.dependencies['previous'] is first
    assert second.previous is first
    assert first.result == 'first ran'


def test_a_dependency_keeps_its_references_to_the_suite(tmp_path, monkeypatch):
    """
    The copies of other steps and of the component that a pickle holds are
    not grafted onto the suite being run.
    """
    monkeypatch.chdir(tmp_path)
    first, second, third = _make_chain(str(tmp_path), length=3)
    _run_chain([first, second])

    os.chdir(third.work_dir)
    load_dependencies(third)

    assert second.dependencies['previous'] is first
    assert second.previous is first
    assert second.component is third.component
    assert second.tasks['task'] is third.tasks['task']
