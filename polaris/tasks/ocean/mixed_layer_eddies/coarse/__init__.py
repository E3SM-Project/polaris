from polaris import Task
from polaris.tasks.ocean.mixed_layer_eddies.coarse.verify import Verify


class Coarse(Task):
    """
    The coarse runs of the mixed-layer eddies tasks, with the submesoscale
    eddy parameterization off and on
    """

    def __init__(self, component, indir, coarse_steps):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        coarse_steps : dict of dict of polaris.Step
            The shared steps at each coarse resolution, keyed by the
            resolution's directory name and then the step name
        """
        super().__init__(component=component, name='coarse', indir=indir)
        for resdir, steps in coarse_steps.items():
            for name, step in steps.items():
                self.add_step(step, symlink=f'{resdir}/{name}')
        self.add_step(
            Verify(
                component=component,
                indir=self.subdir,
                coarse_steps=coarse_steps,
            )
        )
