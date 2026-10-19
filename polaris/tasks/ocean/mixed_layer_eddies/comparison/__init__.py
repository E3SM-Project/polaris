from polaris import Task


class Comparison(Task):
    """
    The comparison of the coarse runs of the mixed-layer eddies tasks with
    the eddy-resolving reference run
    """

    def __init__(self, component, indir, resolved_steps, coarse_steps):
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

        coarse_steps : dict of dict of polaris.Step
            The shared steps at each coarse resolution, keyed by the
            resolution's directory name and then the step name
        """
        super().__init__(component=component, name='comparison', indir=indir)
        for name, step in resolved_steps.items():
            self.add_step(step, symlink=f'resolved/{name}')
        for resdir, steps in coarse_steps.items():
            for name, step in steps.items():
                self.add_step(step, symlink=f'{resdir}/{name}')
