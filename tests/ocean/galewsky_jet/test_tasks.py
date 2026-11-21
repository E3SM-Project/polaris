"""
Unit tests for how the Galewsky jet tasks and their steps are put together
"""

import numpy as np

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.galewsky_jet import add_galewsky_jet_tasks
from polaris.tasks.ocean.galewsky_jet.comparison import (
    AdjustmentAnalysis,
    UnstableAnalysis,
)
from polaris.tasks.ocean.galewsky_jet.diagnostics import contour_levels
from polaris.tasks.ocean.galewsky_jet.forward import Forward
from polaris.tasks.ocean.galewsky_jet.init import Init
from polaris.tasks.ocean.galewsky_jet.steady_state import (
    SteadyStateAnalysis,
    SteadyStateViz,
)


def _get_tasks():
    component = Ocean()
    add_galewsky_jet_tasks(component=component)
    return component


def _steps_of_type(task, step_cls):
    return [step for step in task.steps.values() if type(step) is step_cls]


def test_six_tasks():
    component = _get_tasks()
    expected = [
        f'spherical/{prefix}/galewsky_jet/{name}'
        for prefix in ['icos', 'qu']
        for name in ['steady_state', 'adjustment', 'unstable']
    ]
    for subdir in expected:
        assert subdir in component.tasks


def test_steps_per_resolution():
    component = _get_tasks()
    for prefix in ['icos', 'qu']:
        for name in ['steady_state', 'adjustment', 'unstable']:
            task = component.tasks[f'spherical/{prefix}/galewsky_jet/{name}']
            assert len(_steps_of_type(task, Init)) == 4
            assert len(_steps_of_type(task, Forward)) == 4
            viz = _steps_of_type(task, SteadyStateViz)
            assert len(viz) == (4 if name == 'steady_state' else 0)


def test_init_steps_are_shared_by_perturbed_tasks():
    component = _get_tasks()
    tasks = {
        name: component.tasks[f'spherical/icos/galewsky_jet/{name}']
        for name in ['steady_state', 'adjustment', 'unstable']
    }
    inits = {
        name: {step.subdir for step in _steps_of_type(task, Init)}
        for name, task in tasks.items()
    }
    assert inits['adjustment'] == inits['unstable']
    assert inits['steady_state'].isdisjoint(inits['adjustment'])
    for name, subdirs in inits.items():
        kind = 'balanced' if name == 'steady_state' else 'perturbed'
        assert all(f'/init/{kind}/' in subdir for subdir in subdirs)
        for step in _steps_of_type(tasks[name], Init):
            assert step.perturbed == (name != 'steady_state')


def test_forward_steps_belong_to_one_task():
    component = _get_tasks()
    subdirs = []
    for name in ['steady_state', 'adjustment', 'unstable']:
        task = component.tasks[f'spherical/icos/galewsky_jet/{name}']
        for step in _steps_of_type(task, Forward):
            assert step.task_name == name
            assert step.subdir.startswith(task.subdir)
            subdirs.append(step.subdir)
    assert len(subdirs) == len(set(subdirs))


def test_analysis_step_types():
    component = _get_tasks()
    expected = dict(
        steady_state=SteadyStateAnalysis,
        adjustment=AdjustmentAnalysis,
        unstable=UnstableAnalysis,
    )
    for name, step_cls in expected.items():
        task = component.tasks[f'spherical/qu/galewsky_jet/{name}']
        assert len(_steps_of_type(task, step_cls)) == 1


def test_contour_levels_are_odd_multiples_of_half_interval():
    levels = contour_levels(8.0, np.array([-13.0, 0.0, 21.0]))
    np.testing.assert_allclose(levels, [-20, -12, -4, 4, 12, 20])
    assert len(contour_levels(8.0, np.array([1.0, -3.9]))) == 0
