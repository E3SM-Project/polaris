import os

from polaris.task import Task
from polaris.tasks.mesh.spherical.unified.sizing_field.steps import (
    get_unified_mesh_sizing_field_steps,
)


class SizingFieldTask(Task):
    """
    A standalone task for building one named unified sizing field.

    Parameters
    ----------
    component : polaris.Component
        The component the task belongs to

    mesh_name : str
        The name of the unified mesh
    """

    def __init__(self, component, mesh_name):
        subdir = os.path.join(
            'spherical',
            'unified',
            mesh_name,
            'sizing_field',
            'task',
        )
        super().__init__(
            component=component,
            name=f'sizing_field_{mesh_name}_task',
            subdir=subdir,
        )

        sizing_steps, config = get_unified_mesh_sizing_field_steps(
            mesh_name=mesh_name, include_viz=True
        )
        self.set_shared_config(config, link='sizing_field.cfg')
        for symlink, step in sizing_steps.items():
            self.add_step(step, symlink=symlink)
