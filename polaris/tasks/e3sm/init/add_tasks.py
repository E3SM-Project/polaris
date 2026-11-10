from typing import Dict

from polaris.tasks import TaskGroup, add_task_groups

# The task groups of the e3sm/init component, in the order they are added.
# Nothing here is imported until a task group is added.
TASK_GROUPS: Dict[str, TaskGroup] = {
    'topo/combine': TaskGroup(
        'polaris.tasks.e3sm.init.topo.combine.tasks', 'add_combine_topo_tasks'
    ),
    'topo/remap': TaskGroup(
        'polaris.tasks.e3sm.init.topo.remap.tasks', 'add_remap_topo_tasks'
    ),
    'topo/cull': TaskGroup(
        'polaris.tasks.e3sm.init.topo.cull.tasks', 'add_cull_topo_tasks'
    ),
    'component_inputs': TaskGroup(
        'polaris.tasks.e3sm.init.component_inputs.tasks',
        'add_component_inputs_tasks',
    ),
}


def add_e3sm_init_tasks(component, task_groups=None):
    """
    Add tasks to the e3sm/init component

    Parameters
    ----------
    component : polaris.Component
        the e3sm/init component that the tasks will be added to

    task_groups : list of str, optional
        The task groups to add, by default all of them
    """
    add_task_groups(component, task_groups)
