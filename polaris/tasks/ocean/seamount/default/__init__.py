from polaris import Task as Task
from polaris.tasks.ocean.seamount.forward import Forward as Forward
from polaris.tasks.ocean.seamount.viz import Viz as Viz

# The name of the Omega-only forward step that runs the finite-volume
# horizontal pressure gradient.  The centered step keeps the plain name
# ``forward``: it is the run both models share and the one existing baselines
# hold, so renaming it would silently drop the baseline comparison for the
# scheme that has not changed.
FINITE_VOLUME_STEP = 'forward_finite_volume'


class Default(Task):
    """
    The default seamount test case creates the mesh and initial condition,
    then performs a 6 day forward run and plots the results.

    Under Omega it performs a second forward run with the finite-volume
    horizontal pressure gradient, over the same initial condition, so that
    the two schemes are compared at an identical state.

    Attributes
    ----------
    init : polaris.tasks.ocean.seamount.init.Init
        The shared step for creating the initial state
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
        task_name = 'default'
        super().__init__(component=component, name=task_name, indir=indir)

        self.init = init

        self.add_step(init, symlink='init')

        forward_step = Forward(
            component=component,
            init=init,
            task_name=task_name,
            name='forward',
            indir=self.subdir,
        )
        self.add_step(forward_step)
        # the forward run is 6 days long, so it is worth always producing the
        # plots rather than making the user re-run the task to get them
        self.add_step(Viz(component=component, indir=self.subdir))

    def configure(self):
        """
        Add the finite-volume forward step if the model supports it.

        The scheme exists only in Omega, so the step is added here rather
        than in ``__init__()``: ``configure()`` is the first point at which
        the user's and machine's config options have been merged in and
        ``ocean:model`` is known.  Adding it unconditionally would break the
        task outright for MPAS-Ocean.
        """
        super().configure()

        if self.config.get('ocean', 'model') != 'omega':
            return
        if FINITE_VOLUME_STEP in self.steps:
            return

        # viz reads the forward steps, so it has to stay last
        viz = self.steps['viz']
        self.remove_step(viz)

        self.add_step(
            Forward(
                component=self.component,
                init=self.init,
                task_name=self.name,
                name=FINITE_VOLUME_STEP,
                scheme='finite_volume',
                indir=self.subdir,
            )
        )
        self.add_step(viz)
