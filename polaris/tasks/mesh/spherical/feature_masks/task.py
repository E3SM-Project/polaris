import os

from polaris.config import PolarisConfigParser
from polaris.task import Task
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
)


class FeatureMasksTask(Task):
    """
    A configurable task for creating feature masks on a standard MPAS mesh.
    """

    def __init__(self, component):
        """
        Create a new configurable feature-mask task.
        """
        subdir = os.path.join('spherical', 'feature_masks', 'configurable')
        super().__init__(
            component=component,
            name='feature_masks_task',
            subdir=subdir,
        )

        config = PolarisConfigParser(
            filepath=os.path.join(component.name, subdir, 'feature_masks.cfg')
        )
        config.add_from_package(
            'polaris.tasks.mesh.spherical.feature_masks',
            'feature_masks.cfg',
        )
        self.set_shared_config(config, link='feature_masks.cfg')

        step = ComputeFeatureMasksStep(
            component=component,
            subdir=os.path.join(subdir, 'compute'),
        )
        step.set_shared_config(config, link='feature_masks.cfg')
        self.add_step(step)
