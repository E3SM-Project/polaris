from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES

from .task import RealisticGlobalSshAdjustment


def add_realistic_global_ssh_adjustment_tasks(component):
    """
    Add :py:class:`.RealisticGlobalSshAdjustment` tasks for every supported
    base and unified MPAS mesh.

    The mesh list matches the one used by the ``realistic_global`` init
    workflow.  A task can only be set up for an ocean with ice-shelf cavities.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        component.add_task(
            RealisticGlobalSshAdjustment(
                component=component,
                mesh_name=mesh_name,
            )
        )
