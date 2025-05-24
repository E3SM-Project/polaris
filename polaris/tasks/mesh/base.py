import os

from polaris.mesh.base import get_base_mesh_steps
from polaris.task import Task


def add_base_mesh_tasks(component):
    """
    Add tasks for uniform spherical base meshes to the mesh component

    component : polaris.Component
        the mesh component that the tasks will be added to
    """
    base_mesh_steps = get_base_mesh_steps()
    for base_mesh_step in base_mesh_steps:
        task = BaseMeshTask(component=component, base_mesh_step=base_mesh_step)
        component.add_task(task)


class BaseMeshTask(Task):
    """
    A task for creating a uniform spherical mesh with a given resolution
    """

    def __init__(self, component, base_mesh_step):
        """
        Create the base mesh task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        base_mesh_step : polaris.mesh.spherical.BaseMeshStep
            The base mesh step to use for this task

        """
        # We will take the unusual step of putting the task in a subdirectory
        # of the step because most folks will just run the step directly
        subdir = os.path.join(base_mesh_step.subdir, 'task')
        name = f'{base_mesh_step.name}_task'
        super().__init__(component=component, name=name, subdir=subdir)

        self.set_shared_config(
            config=base_mesh_step.config,
            link=f'{base_mesh_step.mesh_name}.cfg',
        )
        self.add_step(base_mesh_step)
