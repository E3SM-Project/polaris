import os

from polaris.mesh.spherical.unified import (
    RIVER_CONFIG_FILENAME,
)
from polaris.task import Task
from polaris.tasks.mesh.spherical.unified.river.steps import (
    get_unified_mesh_river_steps,
)


class UnifiedRiverNetworkTask(Task):
    """
    A standalone task for preparing all river-network products for one mesh.
    """

    def __init__(self, component, mesh_name):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        mesh_name : str
            The name of the unified mesh
        """
        subdir = os.path.join(
            'spherical', 'unified', mesh_name, 'river', 'task'
        )
        super().__init__(
            component=component,
            name=f'river_network_{mesh_name}_task',
            subdir=subdir,
        )

        steps, river_config = get_unified_mesh_river_steps(
            mesh_name=mesh_name, include_viz=True
        )

        self.set_shared_config(river_config, link=RIVER_CONFIG_FILENAME)

        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
