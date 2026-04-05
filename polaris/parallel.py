from polaris.config import PolarisConfigParser


def set_parallel_systems(tasks, config: PolarisConfigParser):
    """
    Set the active parallel system on every component referenced by the task
    and step graph.

    Parameters
    ----------
    tasks : dict of polaris.Task
        Tasks to scan for referenced components

    config : polaris.config.PolarisConfigParser
        The config to use in constructing the parallel systems
    """
    seen_components: set[int] = set()
    seen_steps: set[int] = set()

    for task in tasks.values():
        _set_parallel_system_for_component(
            task.component, config, seen_components
        )
        for step in task.steps.values():
            _set_parallel_systems_for_step(
                step, config, seen_components, seen_steps
            )


def _set_parallel_systems_for_step(
    step, config: PolarisConfigParser, seen_components, seen_steps
):
    """
    Set the active parallel system on a step's component and recursively on
    the components of any step dependencies.

    Parameters
    ----------
    step : polaris.Step
        The step to scan

    config : polaris.config.PolarisConfigParser
        The config to use in constructing the parallel systems

    seen_components : set of int
        The ids of components that have already been initialized

    seen_steps : set of int
        The ids of steps that have already been visited
    """
    step_id = id(step)
    if step_id in seen_steps:
        return
    seen_steps.add(step_id)

    _set_parallel_system_for_component(step.component, config, seen_components)

    for dependency in step.dependencies.values():
        _set_parallel_systems_for_step(
            dependency, config, seen_components, seen_steps
        )


def _set_parallel_system_for_component(
    component, config: PolarisConfigParser, seen_components
):
    """
    Set the active parallel system for a component once.

    Parameters
    ----------
    component : polaris.Component
        The component to initialize

    config : polaris.config.PolarisConfigParser
        The config to use in constructing the parallel system

    seen_components : set of int
        The ids of components that have already been initialized
    """
    component_id = id(component)
    if component_id in seen_components:
        return

    seen_components.add(component_id)
    component.set_parallel_system(config)
