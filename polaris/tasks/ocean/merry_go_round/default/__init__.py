from polaris import Task
from polaris.ocean.tasks.merry_go_round.forward import Forward


class Default(Task):
    """
    The default test case for the merry-go-round simply ...
    """

    def __init__(self, component, resolution, indir, init):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.merry_go_round.init.Init
            A shared step for creating the initial state
        """
        super().__init__(component=component, name='default', indir=indir)

        self.add_step(init, symlink='init')

        self.add_step(
            Forward(
                component=component,
                refinement='both',
                refinement_factor=1,
                name='default',
                subdir=self.subdir,
                init=init,
            )
        )

        """
        self.add_step(
            Viz(component=component, indir=self.subdir)
        )
        """
