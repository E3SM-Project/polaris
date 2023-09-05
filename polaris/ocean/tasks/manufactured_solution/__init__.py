from polaris.ocean.tasks.manufactured_solution.convergence import Convergence


def add_manufactured_solution_tasks(component):
    """
    Add a task that defines a convergence test that uses the method of
    manufactured solutions

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(Convergence(component=component))
