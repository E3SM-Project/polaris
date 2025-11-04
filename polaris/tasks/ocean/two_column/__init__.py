from polaris.tasks.ocean.two_column.teos10 import Teos10


def add_two_column_tasks(component):
    """
    Add tasks for various tests involving two adjacent ocean columns

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    component.add_task(Teos10(component=component))
