from polaris import Task
from polaris.tasks.ocean.realistic_global.models import (
    DEFAULT_MODEL,
    get_configured_model,
    model_subdir,
    replace_steps,
)

from .schedule import load_schedule_stages
from .steps import (
    CONFIG_FILENAME,
    adjustment_subdir,
    get_dynamic_adjustment_config,
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

    The stages are built at construction from the built-in schedule, for
    :py:data:`~polaris.tasks.ocean.realistic_global.models.DEFAULT_MODEL`, so
    ``polaris list`` shows a representative set.  ``configure`` rebuilds them
    if the configured model is another, or if a user's setup-time config
    changed the schedule.  The number of stages is therefore fixed at setup
    time, not run time.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    model : str
        The ocean model the task's steps are for.

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
        super().__init__(
            component=component,
            name='realistic_global_dynamic_adjustment',
            subdir=adjustment_subdir(mesh_name),
        )
        self.mesh_name = mesh_name
        self.model = DEFAULT_MODEL

        steps, config, stages = get_realistic_dynamic_adjustment_steps(
            component=component,
            mesh_name=mesh_name,
            include_viz=True,
            model=self.model,
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)
        self.stages = stages
        self._adjustment_steps = steps
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)

    def configure(self):
        """
        Rebuild the steps for the configured model, or for a changed schedule.

        Nothing is rebuilt when neither has changed, which is the usual case
        for MPAS-Ocean.

        For another model, the task swaps every model-dependent step,
        including the init chain's, for that model's.  Its config is new and
        has none of the options setup gave this task's config before
        ``configure()``, such as the user's, and the schedule is read from it
        here.  So it starts from this task's config, beneath its own options.

        A schedule that has changed for the same model cannot simply be
        re-requested: the shared steps are keyed by work directory, so a stage
        whose name survived the change would come back carrying its old run
        duration and time step.  The model's adjustment steps are therefore
        dropped first, which :py:meth:`polaris.Task.remove_step` carries
        through to the component once no task is left using them.  The init
        chain stays: it does not depend on the schedule, and a consumer
        holding those step instances would be left with stale ones.
        """
        super().configure()
        model = get_configured_model(self.config, self.model)
        if model == self.model:
            stages = load_schedule_stages(self.mesh_name, self.config)
            if stages == self.stages:
                return
            base = model_subdir(adjustment_subdir(self.mesh_name), model)
            for step in list(self.steps.values()):
                if step.subdir.startswith(f'{base}/'):
                    self.remove_step(step)
        else:
            config = get_dynamic_adjustment_config(
                self.component, self.mesh_name, model
            )
            config.prepend(self.config)

        steps, config, self.stages = get_realistic_dynamic_adjustment_steps(
            component=self.component,
            mesh_name=self.mesh_name,
            include_viz=True,
            model=model,
        )
        replace_steps(self, self._adjustment_steps, steps)
        self._adjustment_steps = steps
        self.set_shared_config(config, link=CONFIG_FILENAME)
        self.model = model
