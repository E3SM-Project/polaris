from polaris import Task
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
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

        steps, config = get_woa23_steps(
            component=component,
            include_viz=True,
        )
        self.set_shared_config(config)

        for symlink, step in steps.items():
            self.add_step(
                step, symlink=symlink, run_by_default=symlink != 'woa23_viz'
            )
            if step.name in ['woa23_combine', 'woa23_extrapolate']:
                # these are usually cached but not in this standalone task
                self.free_running_steps.add(step.subdir)
