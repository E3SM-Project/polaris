import pytest

from polaris import Component, Step


def _step(component, name):
    return Step(component=component, name=name, subdir=name)


def test_add_dependency_wires_the_files_that_carry_it():
    component = Component(name='component')
    step = _step(component, 'consumer')
    dependency = _step(component, 'producer')
    step.add_dependency(dependency)

    assert step.dependencies['producer'] is dependency
    assert dependency.is_dependency
    assert 'step_after_run.pickle' in dependency.outputs
    assert len(step.input_data) == 1


def test_add_dependency_is_idempotent_for_the_same_step():
    """
    A get_*_steps() helper that wires a dependency outside a step constructor
    is called once per consumer, since the steps themselves are shared.  Asking
    for the same wiring again has to be a no-op rather than an error -- and a
    no-op all the way down, since neither add_output_file() nor
    add_input_file() de-duplicates.
    """
    component = Component(name='component')
    step = _step(component, 'consumer')
    dependency = _step(component, 'producer')

    step.add_dependency(dependency)
    step.add_dependency(dependency)

    assert step.dependencies == {'producer': dependency}
    assert dependency.outputs.count('step_after_run.pickle') == 1
    assert len(step.input_data) == 1


def test_add_dependency_still_rejects_a_different_step():
    """
    The error worth keeping is the name collision the ``name`` argument exists
    to resolve, not the repeat request.
    """
    component = Component(name='component')
    step = _step(component, 'consumer')
    first = _step(component, 'producer')
    second = _step(component, 'other')

    step.add_dependency(first)
    with pytest.raises(ValueError, match='different dependency'):
        step.add_dependency(second, name='producer')

    assert step.dependencies['producer'] is first
