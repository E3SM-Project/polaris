from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from polaris.component import Component
    from polaris.step import Step


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
    components, _ = _walk_tasks(tasks)
    return components


def get_steps_by_component(tasks):
    """
    Get the steps in the given tasks and in their dependencies, grouped by the
    component that owns each step.

    Every component in use has an entry, even if it owns no steps.

    Parameters
    ----------
    tasks : dict of polaris.Task
        Tasks to scan for steps

    Returns
    -------
    steps_by_component : dict of list of polaris.Step
        The steps each component owns, with the component names as keys
    """
    _, steps_by_component = _walk_tasks(tasks)
    return steps_by_component


def _walk_tasks(tasks):
    """
    Walk the task and step graph, collecting the components in use and the
    steps each of them owns
    """
    components: List['Component'] = list()
    steps_by_component: Dict[str, List['Step']] = dict()
    seen_components: set[int] = set()
    seen_steps: set[int] = set()

    for task in tasks.values():
        _add_component(
            task.component, components, steps_by_component, seen_components
        )
        for step in task.steps.values():
            _add_step(
                step,
                components,
                steps_by_component,
                seen_components,
                seen_steps,
            )

    return components, steps_by_component


def _add_step(
    step, components, steps_by_component, seen_components, seen_steps
):
    """
    Add a step and its dependencies to the components that own them
    """
    step_id = id(step)
    if step_id in seen_steps:
        return
    seen_steps.add(step_id)

    _add_component(
        step.component, components, steps_by_component, seen_components
    )
    steps_by_component[step.component.name].append(step)

    for dependency in step.dependencies.values():
        _add_step(
            dependency,
            components,
            steps_by_component,
            seen_components,
            seen_steps,
        )


def _add_component(component, components, steps_by_component, seen_components):
    """Add a component to ``components`` if it is not already there"""
    component_id = id(component)
    if component_id in seen_components:
        return

    seen_components.add(component_id)
    components.append(component)
    steps_by_component[component.name] = list()
