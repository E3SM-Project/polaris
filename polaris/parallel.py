import inspect

import mache
from mache.parallel import ParallelSystem

from polaris.component_graph import get_components_in_use
from polaris.config import PolarisConfigParser


def check_mache_supports_placement():
    """
    Check that the installed mache can confine a launch to part of an
    allocation.

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
        If the installed mache has no placement support
    """
    parameters = inspect.signature(
        ParallelSystem.get_parallel_command
    ).parameters
    if 'placement' in parameters:
        return

    raise RuntimeError(
        f'The installed mache ({mache.__version__}) cannot confine a launch '
        f'to part of an allocation, which Polaris now requires.\n'
        f'Install mache 3.12.0 or later.'
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

    for component in get_components_in_use(tasks):
        component.set_parallel_system(config)
