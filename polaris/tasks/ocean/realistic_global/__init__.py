from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    Woa23 as Woa23,
)


def add_realistic_global_tasks(component):
    """
    Add tasks for realistic global ocean preprocessing and initialization.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    component.add_task(Woa23(component=component))
