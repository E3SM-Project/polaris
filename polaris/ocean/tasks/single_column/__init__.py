from polaris.ocean.tasks.single_column.cvmix import CVMix
from polaris.ocean.tasks.single_column.ideal_age import IdealAge


def add_single_column_tasks(component):
    """
    Add tasks for various single-column tests

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    component.add_task(CVMix(component=component))
    component.add_task(IdealAge(component=component))
