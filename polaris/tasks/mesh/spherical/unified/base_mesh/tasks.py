from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.base_mesh.task import BaseMeshTask


def add_unified_base_mesh_tasks(component):
    """
    Add standalone base-mesh tasks for the supported unified meshes.

    Parameters
    ----------
    component : polaris.Component
        The component to which the tasks will be added.
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            BaseMeshTask(component=component, mesh_name=mesh_name)
        )
