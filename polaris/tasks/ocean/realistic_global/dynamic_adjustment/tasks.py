from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES

from .task import RealisticGlobalDynamicAdjustment


def add_realistic_global_dynamic_adjustment_tasks(component):
    """
    Add :py:class:`.RealisticGlobalDynamicAdjustment` tasks for every supported
    base and unified MPAS mesh.

    The mesh list matches the one used by the ``realistic_global`` init and
    forward workflows, so that every mesh with a realistic initial condition
    also gets a dynamic-adjustment task.  Meshes without a mesh-specific
    schedule fall back to the coarse ``default.yaml``.

    The target ocean model is resolved from the ``[ocean] model`` config option
    during component setup.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        component.add_task(
            RealisticGlobalDynamicAdjustment(
                component=component,
                mesh_name=mesh_name,
            )
        )
