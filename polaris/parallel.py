from polaris.component_graph import get_components_in_use
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
    for component in get_components_in_use(tasks):
        component.set_parallel_system(config)
