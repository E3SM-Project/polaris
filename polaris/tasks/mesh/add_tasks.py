from polaris.tasks.mesh.base import add_base_mesh_tasks
from polaris.tasks.mesh.spherical.feature_masks import add_feature_mask_tasks
from polaris.tasks.mesh.spherical.unified.base_mesh import (
    add_unified_base_mesh_tasks,
)
from polaris.tasks.mesh.spherical.unified.coastline import (
    add_coastline_tasks,
)
from polaris.tasks.mesh.spherical.unified.river import add_river_tasks
from polaris.tasks.mesh.spherical.unified.sizing_field import (
    add_sizing_field_tasks,
)


def add_mesh_tasks(component):
    """
    Add all tasks to the mesh component

    component : polaris.Component
        the mesh component that the tasks will be added to
    """
    # add tasks alphabetically (by name in work directory)
    add_base_mesh_tasks(component=component)
    add_unified_base_mesh_tasks(component=component)
    add_coastline_tasks(component=component)
    add_feature_mask_tasks(component=component)
    add_river_tasks(component=component)
    add_sizing_field_tasks(component=component)
