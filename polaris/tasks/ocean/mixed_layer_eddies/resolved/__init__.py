from polaris import Task
from polaris.tasks.ocean.mixed_layer_eddies.resolved.analysis import (
    Analysis,
)


class Resolved(Task):
    """
    The eddy-resolving reference run of the mixed-layer eddies tasks
    """

    def __init__(self, component, indir, resolved_steps):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        resolved_steps : dict of polaris.Step
            The shared ``init`` step and the forward steps of each segment of
            the resolved run
        """
        super().__init__(component=component, name='resolved', indir=indir)
        for name, step in resolved_steps.items():
            self.add_step(
                step, symlink=name, run_by_default=name != 'extended'
            )
        self.add_step(
            Analysis(
                component=component,
                indir=self.subdir,
                resolved_steps=resolved_steps,
            )
        )
