from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.sizing_field.task import (
    SizingFieldTask,
)


def add_sizing_field_tasks(component):
    """
    Add standalone sizing-field tasks for all supported unified meshes.

    One :py:class:`SizingFieldTask` is registered for each mesh name in
    :py:data:`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`.

    Parameters
    ----------
    component : polaris.Component
        The component to register the tasks with
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            SizingFieldTask(component=component, mesh_name=mesh_name)
        )
