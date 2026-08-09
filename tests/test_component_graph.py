from polaris import Component, Step, Task
from polaris.component_graph import (
    get_components_in_use,
    get_steps_by_component,
)


def get_task(component, name, steps=()):
    """Build a task in ``component`` containing ``steps``"""
    task = Task(component=component, name=name)
    for step in steps:
        task.add_step(step=step)
    return task


def test_the_task_component_is_in_use():
    """A task with no steps still puts its own component in use."""
    ocean = Component(name='ocean')
    task = get_task(ocean, 'a_task')

    assert get_components_in_use({task.path: task}) == [ocean]


def test_a_step_from_another_component_is_in_use():
    """
    A task that includes a step from another component puts that component in
    use, too.  This is what makes a cross-component task possible.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    step = Step(component=ocean, name='a_shared_step')
    task = get_task(e3sm_init, 'a_task', steps=[step])

    assert get_components_in_use({task.path: task}) == [e3sm_init, ocean]


def test_the_component_of_a_dependency_is_in_use():
    """
    A step's dependencies may live in yet another component, which is in use
    even though no task refers to it directly.
    """
    ocean = Component(name='ocean')
    mesh = Component(name='mesh')
    e3sm_init = Component(name='e3sm/init')
    dependency = Step(component=mesh, name='a_mesh_step')
    step = Step(component=ocean, name='a_shared_step')
    step.add_dependency(dependency)
    task = get_task(e3sm_init, 'a_task', steps=[step])

    components = get_components_in_use({task.path: task})

    assert components == [e3sm_init, ocean, mesh]


def test_each_component_appears_once():
    """
    Components are not repeated, however many tasks and steps refer to them,
    and the order they were encountered in is preserved.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    first = get_task(
        e3sm_init, 'first', steps=[Step(component=ocean, name='first_step')]
    )
    second = get_task(
        ocean, 'second', steps=[Step(component=ocean, name='second_step')]
    )
    tasks = {first.path: first, second.path: second}

    assert get_components_in_use(tasks) == [e3sm_init, ocean]


def test_steps_are_grouped_by_the_component_that_owns_them():
    """
    Each step goes with its own component, not with the component of the task
    it belongs to.  This is what a component's configure() method is given.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    ocean_step = Step(component=ocean, name='an_ocean_step')
    e3sm_init_step = Step(component=e3sm_init, name='an_e3sm_init_step')
    task = get_task(e3sm_init, 'a_task', steps=[ocean_step, e3sm_init_step])

    steps_by_component = get_steps_by_component({task.path: task})

    assert steps_by_component == {
        'e3sm/init': [e3sm_init_step],
        'ocean': [ocean_step],
    }


def test_a_component_with_no_steps_has_an_entry():
    """
    The component that owns a task always has an entry, so that its
    configure() method gets called with an empty list rather than not at all.
    """
    mesh = Component(name='mesh')
    task = get_task(mesh, 'a_task')

    assert get_steps_by_component({task.path: task}) == {'mesh': []}


def test_a_circular_dependency_does_not_recurse_forever():
    """
    Steps that depend on one another are visited once each.
    """
    ocean = Component(name='ocean')
    first = Step(component=ocean, name='first_step')
    second = Step(component=ocean, name='second_step')
    first.add_dependency(second)
    second.add_dependency(first)
    task = get_task(ocean, 'a_task', steps=[first, second])

    assert get_components_in_use({task.path: task}) == [ocean]
