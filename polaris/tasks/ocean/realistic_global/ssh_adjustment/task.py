from polaris import Task
from polaris.tasks.ocean.realistic_global.cavities import (
    check_cavities_supported,
    has_ice_shelf_cavities,
)
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
)
from polaris.tasks.ocean.realistic_global.models import DEFAULT_MODEL

from .steps import (
    CONFIG_FILENAME,
    get_realistic_ssh_adjustment_steps,
    ssh_adjustment_subdir,
)


class RealisticGlobalSshAdjustment(Task):
    """
    The adjustment of the SSH under land ice to the land-ice pressure for a
    realistic global ocean with ice-shelf cavities on one MPAS mesh.

    The adjusted initial state is what every ``realistic_global`` ocean run
    with cavities starts from.  The steps are shared component steps built by
    :py:func:`.get_realistic_ssh_adjustment_steps`, so those runs get the same
    instances; this task is the way to run them on their own.

    The ocean has cavities only when a user's config sets an Antarctic
    boundary convention that has them, and only MPAS-Ocean supports them, so
    the task can only be set up with such a config.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.
    """

    def __init__(self, component, mesh_name):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.

        mesh_name : str
            The name of the MPAS mesh (e.g. ``'qu240km'``).
        """
        super().__init__(
            component=component,
            name='realistic_global_ssh_adjustment',
            subdir=ssh_adjustment_subdir(mesh_name),
        )
        self.mesh_name = mesh_name

        init_steps, _ = get_realistic_init_steps(
            component=component,
            mesh_name=mesh_name,
            include_viz=False,
            model=DEFAULT_MODEL,
        )
        for symlink, step in init_steps.items():
            self.add_step(step, symlink=symlink)

        steps, config, _ = get_realistic_ssh_adjustment_steps(
            component=component, mesh_name=mesh_name, model=DEFAULT_MODEL
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)
        for name, step in steps.items():
            self.add_step(step, symlink=name)

    def configure(self):
        """
        Check that the ocean has ice-shelf cavities and that the ocean model
        supports them.
        """
        super().configure()
        check_cavities_supported(self.config)
        if not has_ice_shelf_cavities(self.config):
            raise ValueError(
                f'{self.path} only runs for an ocean with ice-shelf cavities: '
                f'set [spherical_mesh] antarctic_boundary_convention to '
                f'grounding_line or bedrock_zero in a user config file.'
            )
