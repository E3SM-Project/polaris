from polaris import Task
from polaris.tasks.landice.mismip_plus.analysis import Analysis


class ExperimentTask(Task):
    """
    A task for running a MISMIP+ experiment from the steady state and
    comparing it with Cornford et al. (2020)

    Attributes
    ----------
    experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
        The experiment
    """

    def __init__(
        self, component, experiment, shared_steps, forward, previous, indir
    ):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.landice.Landice
            The landice component that this task belongs to

        experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
            The experiment

        shared_steps : dict of str to polaris.Step
            The shared steps: ``mesh``, ``init``, ``spin_up_run``,
            ``spin_up`` and ``cornford2020``

        forward : polaris.tasks.landice.mismip_plus.forward.Forward
            The shared step that runs the experiment

        previous : polaris.tasks.landice.mismip_plus.forward.Forward or None
            The shared step of the experiment this one starts from, if any

        indir : str
            The directory the task is in, to which ``name`` will be appended
        """
        super().__init__(
            component=component, name=experiment.subdir, indir=indir
        )
        self.experiment = experiment

        # these steps are left out when the steady state comes from the cache
        for name in ['mesh', 'init', 'spin_up_run', 'spin_up']:
            self.add_step(shared_steps[name], symlink=name)

        if previous is not None:
            self.add_step(previous, symlink=previous.name)
        # the forward step is in this task's directory
        self.add_step(forward)

        cornford = shared_steps['cornford2020']
        self.add_step(cornford, symlink='cornford2020')

        self.add_step(
            Analysis(
                component=component,
                experiment=experiment,
                indir=self.subdir,
                spin_up=shared_steps['spin_up'],
                forward=forward,
                cornford=cornford,
                previous=previous,
            )
        )
