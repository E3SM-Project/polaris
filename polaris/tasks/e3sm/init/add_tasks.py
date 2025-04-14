from polaris.tasks.e3sm.init.topo.combine import CombineTask as CombineTopoTask


def add_e3sm_init_tasks(component):
    """
    Add all tasks to the e3sm/init component

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    component.add_task(CombineTopoTask(component=component))
