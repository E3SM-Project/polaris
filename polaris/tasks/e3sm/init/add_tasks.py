from polaris.tasks.e3sm.init.topo.combine import CombineTask as CombineTopoTask
from polaris.tasks.e3sm.init.topo.remap import add_remap_topo_tasks


def add_e3sm_init_tasks(component):
    """
    Add all tasks to the e3sm/init component

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    for low_res in [False, True]:
        component.add_task(
            CombineTopoTask(component=component, low_res=low_res)
        )

    add_remap_topo_tasks(component=component)
