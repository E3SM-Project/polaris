from typing import Dict

from polaris.tasks import TaskGroup, add_task_groups

# The task groups of the seaice component, in the order they are added
# (alphabetically).  Nothing here is imported until a task group is added.
TASK_GROUPS: Dict[str, TaskGroup] = {
    'single_column': TaskGroup(
        'polaris.tasks.seaice.single_column', 'add_single_column_tasks'
    ),
}


def add_seaice_tasks(component, task_groups=None):
    """
    Add tasks to the seaice component

    Parameters
    ----------
    component : polaris.Component
        the seaice component that the tasks will be added to

    task_groups : list of str, optional
        The task groups to add, by default all of them
    """
    add_task_groups(component, task_groups)
