from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
    min_res_for_mesh,
)

from .initial_condition import StepInitialCondition
from .task import RealisticGlobalForward


def add_realistic_global_forward_tasks(component):
    """
    Add :py:class:`.RealisticGlobalForward` tasks for every supported base and
    unified MPAS mesh.

    The mesh list matches the one used by
    :py:func:`polaris.tasks.ocean.realistic_global.init.tasks.add_realistic_global_init_tasks`,
    so that every mesh with a realistic initial condition also gets a
    corresponding forward task.

    The target ocean model is not fixed at registration time; it is resolved
    from the ``[ocean] model`` config option during component setup.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        init_steps, _ = get_realistic_init_steps(
            component=component, mesh_name=mesh_name, include_viz=False
        )
        init_condition = StepInitialCondition(
            init_steps['initial_state'],
            min_res=min_res_for_mesh(mesh_name),
            approx_cell_count=estimate_ocean_cell_count(mesh_name),
            forcing_step=init_steps['forcing'],
        )
        component.add_task(
            RealisticGlobalForward(
                component=component,
                mesh_name=mesh_name,
                init_condition=init_condition,
                init_steps=init_steps,
            )
        )
