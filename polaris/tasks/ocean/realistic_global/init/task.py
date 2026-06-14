from polaris import Task

from .steps import get_realistic_init_steps


class RealisticGlobalInit(Task):
    """
    A task for creating a realistic global ocean initial condition on one
    MPAS mesh for the configured target ocean model.

    The target model is determined by the ``[ocean] model`` config option
    (resolved from ``'detect'`` to ``'omega'`` or ``'mpas-ocean'`` during
    component setup).  All steps up to and including
    :py:class:`.RealisticPStarInitStep` are model-independent; only
    :py:class:`.InitialStateStep` branches on the resolved model at run time.
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
        subdir = f'spherical/realistic_global/init/{mesh_name}/task'
        super().__init__(
            component=component,
            name='realistic_global_init',
            subdir=subdir,
        )

        steps, config = get_realistic_init_steps(
            component=component, mesh_name=mesh_name
        )
        self.set_shared_config(config, link='realistic_global_init.cfg')

        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
