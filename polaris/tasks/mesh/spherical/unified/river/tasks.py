from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.river.task import (
    UnifiedRiverNetworkTask,
)


def add_river_tasks(component):
    """
    Add standalone river-network tasks.

    Parameters
    ----------
    component : polaris.Component
        The mesh component that the tasks belong to
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            UnifiedRiverNetworkTask(component=component, mesh_name=mesh_name)
        )
