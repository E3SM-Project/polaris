from polaris import Task as Task
from polaris.tasks.ocean.seamount.forward import Forward as Forward
from polaris.tasks.ocean.seamount.viz import Viz as Viz


class Short(Task):
    """
    The short seamount test case creates the mesh and initial condition, then
    performs a 1 hour forward run.  It is too short to say anything about the
    pressure gradient error but long enough to catch a regression, so it is
    the variant that belongs in the pull request suites.
    """

    def __init__(self, component, indir, init):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.seamount.init.Init
            A shared step for creating the initial state
        """
        task_name = 'short'
        super().__init__(component=component, name=task_name, indir=indir)

        self.add_step(init, symlink='init')

        forward_step = Forward(
            component=component,
            init=init,
            task_name=task_name,
            name='forward',
            indir=self.subdir,
        )
        self.add_step(forward_step)
        # unlike the default task, the forward run here is cheap to repeat, so
        # the plots are opt-in as they are elsewhere in Polaris
        self.add_step(
            Viz(component=component, indir=self.subdir), run_by_default=False
        )
