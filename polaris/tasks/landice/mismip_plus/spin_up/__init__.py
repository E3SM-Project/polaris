from polaris import Task
from polaris.tasks.landice.mismip_plus.spin_up.run import (
    SpinUpRun as SpinUpRun,
)
from polaris.tasks.landice.mismip_plus.spin_up.spin_up import (
    SpinUp as SpinUp,
)
from polaris.tasks.landice.mismip_plus.spin_up.viz import (
    SpinUpViz as SpinUpViz,
)


class SpinUpTask(Task):
    """
    A task for spinning MALI up to the MISMIP+ steady state
    """

    def __init__(self, component, shared_steps, indir):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.landice.Landice
            The landice component that this task belongs to

        shared_steps : dict of str to polaris.Step
            The shared steps: ``mesh``, ``init``, ``spin_up_run`` and
            ``spin_up``

        indir : str
            The directory the task is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='spin_up', indir=indir)

        self.add_step(shared_steps['mesh'], symlink='mesh')
        self.add_step(shared_steps['init'], symlink='init')
        # the run and spin-up steps are in this task's directory
        self.add_step(shared_steps['spin_up_run'])
        spin_up = shared_steps['spin_up']
        self.add_step(spin_up)
        # this task makes the steady state that others read from the cache
        self.free_running_steps.add(spin_up.subdir)

        self.add_step(
            SpinUpViz(
                component=component,
                run_step=shared_steps['spin_up_run'],
                spin_up=spin_up,
                indir=self.subdir,
            )
        )
