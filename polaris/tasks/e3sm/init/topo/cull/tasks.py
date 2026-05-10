from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.e3sm.init.topo.cull.task import CullTopoTask


def add_cull_topo_tasks(component):
    """
    Add a task to remap topography for each supported base mesh

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        task = CullTopoTask(
            component=component,
            mesh_name=mesh_name,
            include_viz=True,
        )
        component.add_task(task)
