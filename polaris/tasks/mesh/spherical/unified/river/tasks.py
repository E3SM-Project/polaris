from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.river.task import (
    LatLonRiverNetworkTask,
    PrepareRiverNetworkTask,
)


def add_river_tasks(component):
    """
    Add standalone river-network tasks.
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            PrepareRiverNetworkTask(component=component, mesh_name=mesh_name)
        )
        component.add_task(
            LatLonRiverNetworkTask(component=component, mesh_name=mesh_name)
        )
