from polaris import Task
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
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
        subdir = 'spherical/realistic_global/hydrography/woa23'
        super().__init__(component=component, name='woa23', subdir=subdir)

        self.combine_topo_step = get_woa23_topography_step()
        steps, config = get_woa23_steps(
            component=component,
            combine_topo_step=self.combine_topo_step,
        )
        self.set_shared_config(config)

        self.add_step(self.combine_topo_step, symlink='combine_topo')
        for step in steps.values():
            self.add_step(step, run_by_default=step.name != 'viz')
