from polaris import Task
from polaris.tasks.ocean.realistic_global.forcing.jra55.steps import (
    JRA55_SUBDIR,
    get_jra55_steps,
)


class Jra55(Task):
    """
    A task for building a reusable JRA55-do wind-stress product.
    """

    def __init__(self, component):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.
        """
        super().__init__(
            component=component, name='jra55', subdir=JRA55_SUBDIR
        )

        steps, config = get_jra55_steps(
            component=component,
            include_viz=True,
        )
        self.set_shared_config(config)

        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
            if step.name == 'stress':
                # this task exists to regenerate the product, so the step
                # always runs here, including once it is cached by default
                self.free_running_steps.add(step.subdir)
