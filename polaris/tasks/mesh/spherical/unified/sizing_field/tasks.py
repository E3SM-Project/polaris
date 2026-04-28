from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.sizing_field.task import (
    SizingFieldTask,
)


def add_sizing_field_tasks(component):
    """
    Add standalone sizing-field tasks for the supported unified meshes.
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            SizingFieldTask(component=component, mesh_name=mesh_name)
        )
