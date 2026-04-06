import os

from polaris import Task
from polaris.tasks.ocean.global_ocean.hydrography.woa23.steps import (
    get_woa23_steps,
    get_woa23_topography_step,
)


class Woa23(Task):
    """
    A task for building a reusable WOA23 hydrography product.
    """

    def __init__(self, component):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.
        """
        subdir = 'global_ocean/hydrography/woa23'
        super().__init__(component=component, name='woa23', subdir=subdir)

        self.combine_topo_step = get_woa23_topography_step()
        steps, config = get_woa23_steps(
            component=component,
            combine_topo_step=self.combine_topo_step,
        )
        self.set_shared_config(config)

        self.add_step(self.combine_topo_step, symlink='combine_topo')
        for step in steps:
            self.add_step(step, run_by_default=step.name != 'viz')

    def configure(self):
        """
        Use the cached combined-topography product from ``e3sm/init``.
        """
        super().configure()
        cache_keys = [
            os.path.join(self.combine_topo_step.path, output)
            for output in self.combine_topo_step.outputs
        ]
        cached_files = self.combine_topo_step.component.cached_files
        self.combine_topo_step.cached = all(
            filename in cached_files for filename in cache_keys
        )
