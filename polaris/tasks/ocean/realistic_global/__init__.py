from polaris.tasks.ocean.realistic_global.forcing.jra55 import (
    Jra55 as Jra55,
)
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import (
    CACHED_MESHES,
    add_realistic_global_cached_forward_tasks,
    add_realistic_global_forward_tasks,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    Woa23 as Woa23,
)
from polaris.tasks.ocean.realistic_global.init.tasks import (
    add_realistic_global_init_tasks,
)
from polaris.tasks.ocean.realistic_global.restart import Restart as Restart


def add_realistic_global_tasks(component):
    """
    Add tasks for realistic global ocean preprocessing, initialization, and
    forward runs.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    component.add_task(Woa23(component=component))
    component.add_task(Jra55(component=component))
    add_realistic_global_init_tasks(component=component)
    add_realistic_global_forward_tasks(component=component)
    add_realistic_global_cached_forward_tasks(component=component)

    # the restart task is only defined for the mesh it is cheap enough to run
    # on in the pull-request suite
    mesh_name = 'QU.240km'
    mesh_info = CACHED_MESHES[mesh_name]
    init_condition = DatabaseInitialCondition(
        mesh_name=mesh_name,
        mpaso_id=mesh_info['mpaso_id'],
        omega_id=mesh_info['omega_id'],
        min_res=mesh_info['min_res'],
        approx_cell_count=mesh_info['cell_count'],
    )
    component.add_task(
        Restart(
            component=component,
            mesh_name=mesh_name,
            init_condition=init_condition,
        )
    )
