from polaris.tasks.ocean.realistic_global.forcing.jra55 import (
    Jra55 as Jra55,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import (
    add_realistic_global_cached_forward_tasks,
    add_realistic_global_forward_tasks,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    Woa23 as Woa23,
)
from polaris.tasks.ocean.realistic_global.init.tasks import (
    add_realistic_global_init_tasks,
)


def add_realistic_global_tasks(component):
    """
    Add tasks for realistic global ocean preprocessing, initialization, and
    forward runs.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    component.add_task(Woa23(component=component))
    component.add_task(Jra55(component=component))
    add_realistic_global_init_tasks(component=component)
    add_realistic_global_forward_tasks(component=component)
    add_realistic_global_cached_forward_tasks(component=component)
