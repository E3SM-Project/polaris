from polaris import Task

from .schedule import load_schedule_stages
from .steps import (
    CONFIG_FILENAME,
    adjustment_subdir,
    get_realistic_dynamic_adjustment_steps,
)


class RealisticGlobalDynamicAdjustment(Task):
    """
    A staged dynamic-adjustment run of the configured ocean model for a
    realistic global ocean simulation on one MPAS mesh.

    The steps themselves are shared component steps built by
    :py:func:`.get_realistic_dynamic_adjustment_steps`, so a downstream
    workflow that wants the adjusted restart gets the same instances rather
    than a second copy of the chain.  This task is the standalone way to run
    them, and the only consumer that also wants the ``viz`` figure.

    The stages are built once at construction from the built-in schedule (so
    ``polaris list`` shows a representative set) and rebuilt in ``configure``
    if a user's setup-time config changed the schedule.  The number of stages
    is therefore fixed at setup time, not run time.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.
    """

    def __init__(self, component, mesh_name):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.

        mesh_name : str
            The name of the MPAS mesh (e.g. ``'icos240km'``).
        """
        base = f'spherical/realistic_global/{mesh_name}/dynamic_adjustment'
        super().__init__(
            component=component,
            name='realistic_global_dynamic_adjustment',
            subdir=f'{base}/task',
        )
        self.mesh_name = mesh_name

        steps, config, stages = get_realistic_dynamic_adjustment_steps(
            component=component, mesh_name=mesh_name, include_viz=True
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)
        self.stages = stages
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)

    def configure(self):
        """
        Rebuild the stages if a user's setup-time config changed the schedule.

        Nothing is rebuilt when the schedule is unchanged, which is the usual
        case and the only one a downstream consumer of these shared steps sees.
        A schedule that *has* changed cannot simply be re-requested: the shared
        steps are keyed by work directory, so a stage whose name survived the
        change would come back carrying its old run duration and time step.
        The old ones are therefore dropped first, which
        :py:meth:`polaris.Task.remove_step` carries through to the component
        once no task is left using them.

        Only the steps under this mesh's ``dynamic_adjustment`` directory are
        dropped and added back.  Doing this to the whole task would evict the
        ``init`` chain from the component too, and a consumer holding those
        step instances would be left with stale ones.
        """
        super().configure()
        stages = load_schedule_stages(self.mesh_name, self.config)
        if stages == self.stages:
            return

        base = adjustment_subdir(self.mesh_name)
        for step in list(self.steps.values()):
            if step.subdir.startswith(f'{base}/'):
                self.remove_step(step)

        steps, _, self.stages = get_realistic_dynamic_adjustment_steps(
            component=self.component,
            mesh_name=self.mesh_name,
            include_viz=True,
        )
        for symlink, step in steps.items():
            if step.subdir.startswith(f'{base}/'):
                self.add_step(step, symlink=symlink)
