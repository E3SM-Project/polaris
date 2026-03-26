from polaris.tasks.ocean.global_ocean.hydrography.woa23 import (
    Woa23 as Woa23,
)


def add_global_ocean_tasks(component):
    """
    Add tasks for global-ocean preprocessing and initialization.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    component.add_task(Woa23(component=component))
