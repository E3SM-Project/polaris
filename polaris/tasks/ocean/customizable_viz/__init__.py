import os

from polaris import Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.customizable_viz.viz_horiz_field import (
    VizHorizField as VizHorizField,
)
from polaris.tasks.ocean.customizable_viz.viz_transect import (
    VizTransect as VizTransect,
)


def add_customizable_viz_tasks(component):
    customizable_viz_task = CustomizableViz(component=component)
    component.add_task(customizable_viz_task)


class CustomizableViz(Task):
    """
    A customizable visualization task for MPAS-Ocean output
    """

    def __init__(self, component):
        basedir = 'customizable_viz'
        name = 'customizable_viz'
        super().__init__(component=component, name=name, subdir=basedir)

        config_filename = 'customizable_viz.cfg'
        config = PolarisConfigParser(
            filepath=os.path.join(component.name, config_filename)
        )
        config.add_from_package(
            'polaris.tasks.ocean.customizable_viz', config_filename
        )
        self.set_shared_config(config, link=config_filename)

        viz_step = VizHorizField(
            component=component,
            name='viz_horiz_field',
            indir=self.subdir,
        )
        viz_step.set_shared_config(config, link=config_filename)
        self.add_step(viz_step, run_by_default=True)

        transect_step = VizTransect(
            component=component,
            name='viz_transect',
            indir=self.subdir,
        )
        transect_step.set_shared_config(config, link=config_filename)
        self.add_step(transect_step, run_by_default=False)
