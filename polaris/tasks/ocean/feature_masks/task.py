import os

from polaris.config import PolarisConfigParser
from polaris.task import Task
from polaris.tasks.ocean.feature_masks.compute import (
    ComputeOceanFeatureMasksStep,
)


class OceanFeatureMasksTask(Task):
    """
    A configurable task for creating feature masks on native ocean meshes.
    """

    def __init__(self, component):
        """
        Create a new configurable ocean feature-mask task.
        """
        subdir = os.path.join('feature_masks', 'configurable')
        super().__init__(
            component=component,
            name='ocean_feature_masks_task',
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

        step = ComputeOceanFeatureMasksStep(
            component=component,
            subdir=os.path.join(subdir, 'compute'),
        )
        step.set_shared_config(config, link='feature_masks.cfg')
        self.add_step(step)
