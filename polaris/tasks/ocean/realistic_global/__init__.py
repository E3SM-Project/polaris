from polaris.tasks.ocean.realistic_global.analysis_output import (
    add_realistic_global_analysis_output_tasks,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.tasks import (
    add_realistic_global_dynamic_adjustment_tasks,
)
from polaris.tasks.ocean.realistic_global.forcing.jra55 import (
    Jra55 as Jra55,
)
from polaris.tasks.ocean.realistic_global.forward.task import TIME_INTEGRATORS
from polaris.tasks.ocean.realistic_global.forward.tasks import (
    add_realistic_global_cached_forward_tasks,
    add_realistic_global_forward_tasks,
    get_cached_initial_condition,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    Woa23 as Woa23,
)
from polaris.tasks.ocean.realistic_global.init.tasks import (
    add_realistic_global_init_tasks,
)
from polaris.tasks.ocean.realistic_global.min_level_cell import (
    MinLevelCell as MinLevelCell,
)
from polaris.tasks.ocean.realistic_global.restart import Restart as Restart


def add_realistic_global_tasks(component):
    """
    Add tasks for realistic global ocean preprocessing, initialization,
    forward runs, and dynamic adjustment.

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
    add_realistic_global_analysis_output_tasks(component=component)
    add_realistic_global_dynamic_adjustment_tasks(component=component)

    # the restart and min_level_cell tasks are only defined for the mesh they
    # are cheap enough to run on in a pull-request suite
    mesh_name = 'e3sm-qu240'
    init_condition = get_cached_initial_condition(mesh_name)
    component.add_task(
        Restart(
            component=component,
            mesh_name=mesh_name,
            init_condition=init_condition,
        )
    )
    for time_integrator in TIME_INTEGRATORS:
        component.add_task(
            MinLevelCell(
                component=component,
                mesh_name=mesh_name,
                init_condition=init_condition,
                time_integrator=time_integrator,
            )
        )
