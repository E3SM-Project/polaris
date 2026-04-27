import os

from polaris.task import Task
from polaris.tasks.mesh.spherical.unified.base_mesh.steps import (
    get_unified_base_mesh_steps,
)


class BaseMeshTask(Task):
    """
    A standalone task for creating one named unified base mesh.
    """

    def __init__(self, component, mesh_name):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        mesh_name : str
            The name of the unified mesh.
        """
        subdir = os.path.join(
            'spherical', 'unified', mesh_name, 'base_mesh', 'task'
        )
        super().__init__(
            component=component,
            name=f'base_mesh_{mesh_name}_task',
            subdir=subdir,
        )

        steps, config = get_unified_base_mesh_steps(
            mesh_name=mesh_name, include_viz=True
        )
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
