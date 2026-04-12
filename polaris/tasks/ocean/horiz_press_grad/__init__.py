from polaris.tasks.ocean.horiz_press_grad.task import HorizPressGradTask


def add_horiz_press_grad_tasks(component):
    """
    Add tasks for various tests involving the horizonal pressure-gradient
    acceleration between two adjacent ocean columns

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for name in [
        'salinity_gradient',
        'temperature_gradient',
        'ztilde_gradient',
    ]:
        component.add_task(HorizPressGradTask(component=component, name=name))
