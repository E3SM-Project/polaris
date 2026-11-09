from typing import Dict

from polaris.tasks import TaskGroup, add_task_groups

# The task groups of the mesh component, in the order they are added
# (alphabetically by name in the work directory).  Nothing here is imported
# until a task group is added.
_UNIFIED = 'polaris.tasks.mesh.spherical.unified'
TASK_GROUPS: Dict[str, TaskGroup] = {
    'base': TaskGroup('polaris.tasks.mesh.base', 'add_base_mesh_tasks'),
    'spherical/unified/base_mesh': TaskGroup(
        f'{_UNIFIED}.base_mesh', 'add_unified_base_mesh_tasks'
    ),
    'spherical/unified/coastline': TaskGroup(
        f'{_UNIFIED}.coastline', 'add_coastline_tasks'
    ),
    'spherical/feature_masks': TaskGroup(
        'polaris.tasks.mesh.spherical.feature_masks', 'add_feature_mask_tasks'
    ),
    'spherical/unified/river': TaskGroup(
        f'{_UNIFIED}.river', 'add_river_tasks'
    ),
    'spherical/unified/sizing_field': TaskGroup(
        f'{_UNIFIED}.sizing_field', 'add_sizing_field_tasks'
    ),
}


def add_mesh_tasks(component, task_groups=None):
    """
    Add tasks to the mesh component

    Parameters
    ----------
    component : polaris.Component
        the mesh component that the tasks will be added to

    task_groups : list of str, optional
        The task groups to add, by default all of them
    """
    add_task_groups(component, task_groups)
