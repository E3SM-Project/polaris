from polaris.tasks.ocean.two_column.task import TwoColumnTask


def add_two_column_tasks(component):
    """
    Add tasks for various tests involving two adjacent ocean columns

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for name in ['salinity_gradient', 'ztilde_gradient']:
        component.add_task(TwoColumnTask(component=component, name=name))
