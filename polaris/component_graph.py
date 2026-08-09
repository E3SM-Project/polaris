from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from polaris.component import Component


def get_components_in_use(tasks):
    """
    Get the components referenced by the given tasks: the component of each
    task, of each step in those tasks and, recursively, of each step
    dependency.

    A task may include steps from components other than its own, so this is
    not simply the set of components that own the tasks.

    Parameters
    ----------
    tasks : dict of polaris.Task
        Tasks to scan for referenced components

    Returns
    -------
    components : list of polaris.Component
        The components in use, in the order they were first encountered
    """
    components: List['Component'] = list()
    seen_components: set[int] = set()
    seen_steps: set[int] = set()

    for task in tasks.values():
        _add_component(task.component, components, seen_components)
        for step in task.steps.values():
            _add_step_components(step, components, seen_components, seen_steps)

    return components


def _add_step_components(step, components, seen_components, seen_steps):
    """
    Add a step's component and the components of its dependencies to
    ``components``
    """
    step_id = id(step)
    if step_id in seen_steps:
        return
    seen_steps.add(step_id)

    _add_component(step.component, components, seen_components)

    for dependency in step.dependencies.values():
        _add_step_components(
            dependency, components, seen_components, seen_steps
        )


def _add_component(component, components, seen_components):
    """Add a component to ``components`` if it is not already there"""
    component_id = id(component)
    if component_id in seen_components:
        return

    seen_components.add(component_id)
    components.append(component)
