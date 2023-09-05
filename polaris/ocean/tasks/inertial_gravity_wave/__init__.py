from polaris.ocean.tasks.inertial_gravity_wave.convergence import Convergence


def add_inertial_gravity_wave_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(Convergence(component=component))
