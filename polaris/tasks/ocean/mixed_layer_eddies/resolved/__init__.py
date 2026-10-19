from polaris import Task


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
            The shared ``init``, ``spinup`` and ``eddies`` steps of the
            resolved run
        """
        super().__init__(component=component, name='resolved', indir=indir)
        for name, step in resolved_steps.items():
            self.add_step(step, symlink=name)
