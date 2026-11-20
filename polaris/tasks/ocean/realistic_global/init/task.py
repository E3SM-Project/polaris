from polaris import Task
from polaris.tasks.ocean.realistic_global.models import (
    DEFAULT_MODEL,
    get_configured_model,
    replace_steps,
)

from .steps import CONFIG_FILENAME, get_realistic_init_steps, init_subdir


class RealisticGlobalInit(Task):
    """
    A task for creating a realistic global ocean initial condition on one
    MPAS mesh for the configured target ocean model.

    The target model is determined by the ``[ocean] model`` config option
    (resolved from ``'detect'`` to ``'omega'`` or ``'mpas-ocean'`` during
    component setup).  All steps up to and including
    :py:class:`.RealisticPStarInitStep` are model-neutral.  The task is built
    with the model-dependent steps of
    :py:data:`~polaris.tasks.ocean.realistic_global.models.DEFAULT_MODEL`, and
    ``configure()`` swaps in the configured model's.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    model : str
        The ocean model the task's model-dependent steps are for.
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
            name='realistic_global_init',
            subdir=init_subdir(mesh_name),
        )
        self.mesh_name = mesh_name
        self.model = DEFAULT_MODEL

        steps, config = get_realistic_init_steps(
            component=component,
            mesh_name=mesh_name,
            include_viz=True,
            model=self.model,
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)
        self._init_steps = steps

        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)

    def configure(self):
        """
        Swap in the configured ocean model's model-dependent steps.
        """
        super().configure()
        model = get_configured_model(self.config, self.model)
        if model == self.model:
            return

        steps, _ = get_realistic_init_steps(
            component=self.component,
            mesh_name=self.mesh_name,
            include_viz=True,
            model=model,
        )
        replace_steps(self, self._init_steps, steps)
        self._init_steps = steps
        self.model = model
