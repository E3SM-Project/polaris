from polaris.tasks.ocean.two_column.salinity_gradient import SalinityGradient
from polaris.tasks.ocean.two_column.ztilde_gradient import ZTildeGradient


def add_two_column_tasks(component):
    """
    Add tasks for various tests involving two adjacent ocean columns

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    component.add_task(SalinityGradient(component=component))
    component.add_task(ZTildeGradient(component=component))
