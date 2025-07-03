from polaris import Task
from polaris.ocean.tasks.customizable_viz.viz import Viz as Viz


def add_customizable_viz_tasks(component):
    component.add_task(CustomizableViz(component=component))


class CustomizableViz(Task):
    """
    The convergence test case using the method of manufactured solutions
    """

    def __init__(self, component):
        basedir = 'customizable_viz'
        name = 'customizable_viz'
        super().__init__(component=component, name=name, subdir=basedir)
        self.add_step(
            Viz(
                component=component,
                subdir=self.subdir,
            ),
            run_by_default=True,
        )
