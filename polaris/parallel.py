import inspect

import mache
from mache.parallel import ParallelSystem, ResourcePlacement

from polaris.config import PolarisConfigParser


def check_mache_supports_placement():
    """
    Check that the installed mache can confine a launch to part of an
    allocation, and can do it a node at a time.

    A mache without placement takes none of the arguments Polaris now passes
    it, so a run against one fails partway through with a ``TypeError`` from
    deep inside the launcher rather than saying what is wrong.  Worse, a
    future mache that accepted the argument and ignored it would let a run
    appear to work while oversubscribing the machine -- no error, wrong
    results, and slower than running one step at a time.  Both are much
    better caught here.

    Raises
    ------
    RuntimeError
        If the installed mache has no placement support, or expresses a
        placement's cores as one set for the whole launch
    """
    parameters = inspect.signature(
        ParallelSystem.get_parallel_command
    ).parameters
    if 'placement' not in parameters:
        raise RuntimeError(
            f'The installed mache ({mache.__version__}) cannot confine a '
            f'launch to part of an allocation, which Polaris now requires.\n'
            f'Install mache 3.13.0 or later.'
        )

    _check_placement_cores_are_per_node()


def _check_placement_cores_are_per_node():
    """
    Check that a placement's cores are one set per node.

    An earlier mache took one flat set of unique cores for the whole launch,
    which cannot describe a launch spanning nodes on the machines whose
    launchers bind cores explicitly: core numbers are node-local, so two
    nodes both using core 0 is the ordinary case and a single set forbids
    it.

    This builds exactly that -- two nodes, each offering core 0 -- rather
    than reading a version, for the same reason the check above does: the
    capability is what matters and a version is only a proxy for it.
    """
    try:
        placement = ResourcePlacement(nodes=('a', 'b'), cores=((0,), (0,)))
        total_cores = placement.total_cores
    except (AttributeError, TypeError, ValueError) as exception:
        raise RuntimeError(
            f'The installed mache ({mache.__version__}) expresses a '
            f"placement's cores as one set for the whole launch, so Polaris "
            f'cannot place a step across nodes.\n'
            f'Install mache 3.13.0 or later.'
        ) from exception

    if total_cores != 2:
        raise RuntimeError(
            f'The installed mache ({mache.__version__}) accepted a placement '
            f'of one core on each of two nodes and reported {total_cores} '
            f'cores rather than 2, so Polaris cannot rely on what a '
            f'placement means.\n'
            f'Install mache 3.13.0 or later.'
        )


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
    check_mache_supports_placement()

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
