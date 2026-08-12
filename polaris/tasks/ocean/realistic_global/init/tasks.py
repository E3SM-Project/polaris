from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES

from .task import RealisticGlobalInit


def add_realistic_global_init_tasks(component):
    """
    Add :py:class:`.RealisticGlobalInit` tasks for every supported base and
    unified MPAS mesh.

    The mesh list matches the one used by
    :py:func:`polaris.tasks.e3sm.init.topo.cull.tasks.add_cull_topo_tasks`,
    so that every mesh with a culled topography also gets a corresponding
    realistic ocean initialisation task.

    The target ocean model is not fixed at registration time; it is resolved
    from the ``[ocean] model`` config option during component setup.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        component.add_task(
            RealisticGlobalInit(
                component=component,
                mesh_name=mesh_name,
            )
        )
