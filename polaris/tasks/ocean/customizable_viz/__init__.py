from polaris import Task
from polaris.tasks.ocean.customizable_viz.viz_horiz_field import (
    VizHorizField as VizHorizField,
)
from polaris.tasks.ocean.customizable_viz.viz_transect import (
    VizTransect as VizTransect,
)


def add_customizable_viz_tasks(component):
    """
    Add a customizable visualization task for MPAS output
    """
    customizable_viz_task = CustomizableViz(component=component)
    component.add_task(customizable_viz_task)


class CustomizableViz(Task):
    """
    A customizable visualization task for MPAS output
    """

    def __init__(self, component):
        basedir = 'customizable_viz'
        name = 'customizable_viz'
        super().__init__(component=component, name=name, subdir=basedir)

        config_filename = 'customizable_viz.cfg'
        self.config.add_from_package(
            'polaris.tasks.ocean.customizable_viz', config_filename
        )

        viz_step = VizHorizField(
            component=component,
            name='viz_horiz_field',
            indir=self.subdir,
        )
        self.add_step(viz_step, run_by_default=True)

        transect_step = VizTransect(
            component=component,
            name='viz_transect',
            indir=self.subdir,
        )
        self.add_step(transect_step, run_by_default=False)
