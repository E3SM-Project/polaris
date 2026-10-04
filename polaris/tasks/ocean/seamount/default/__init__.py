from polaris import Task as Task
from polaris.tasks.ocean.seamount.analysis import Analysis as Analysis
from polaris.tasks.ocean.seamount.forward import Forward as Forward
from polaris.tasks.ocean.seamount.forward import (
    forward_step_name as forward_step_name,
)
from polaris.tasks.ocean.seamount.viz import Viz as Viz

# The scheme both models share and every task runs
DEFAULT_SCHEME = 'centered'

# The schemes only Omega has.  MPAS-Ocean runs the centered one alone, and
# the task must stay runnable there rather than gaining a step it cannot run.
OMEGA_ONLY_SCHEMES = ['finite_volume']


class Default(Task):
    """
    The default seamount test case creates the mesh and initial condition,
    then performs a 6 day forward run, plots the results and measures the
    spurious circulation.

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
        self._add_scheme_steps(DEFAULT_SCHEME)

    def configure(self):
        """
        Add the steps for the schemes only Omega has, and the analysis step
        that compares whichever schemes were run.

        These are added here rather than in ``__init__()`` because
        ``configure()`` is the first point at which the user's and machine's
        config options have been merged in and ``ocean:model`` is known.
        Adding an Omega-only scheme unconditionally would break the task
        outright for MPAS-Ocean.
        """
        super().configure()

        if 'analysis' in self.steps:
            # already configured
            return

        schemes = [DEFAULT_SCHEME]
        if self.config.get('ocean', 'model') == 'omega':
            for scheme in OMEGA_ONLY_SCHEMES:
                self._add_scheme_steps(scheme)
                schemes.append(scheme)

        self.add_step(
            Analysis(
                component=self.component,
                indir=self.subdir,
                schemes=schemes,
            )
        )

    def _add_scheme_steps(self, scheme):
        """
        Add the forward and viz steps for one pressure-gradient scheme.
        """
        self.add_step(
            Forward(
                component=self.component,
                init=self.init,
                task_name=self.name,
                name=forward_step_name(scheme),
                scheme=scheme,
                indir=self.subdir,
            )
        )
        # the forward run is 6 days long, so it is worth always producing the
        # plots rather than making the user re-run the task to get them
        self.add_step(
            Viz(
                component=self.component,
                indir=self.subdir,
                scheme=scheme,
            )
        )
