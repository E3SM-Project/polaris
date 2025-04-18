import os

from polaris.mesh.add_step import add_uniform_spherical_base_mesh_step
from polaris.task import Task


def add_base_mesh_tasks(component):
    """
    Add tasks for uniform spherical base meshes to the mesh component

    component : polaris.Component
        the mesh component that the tasks will be added to
    """
    for icosahedral in [True, False]:
        for resolution in [480.0, 240.0, 120.0, 60.0, 30.0]:
            task = BaseMeshTask(
                component=component,
                resolution=resolution,
                icosahedral=icosahedral,
            )
            component.add_task(task)


class BaseMeshTask(Task):
    """
    A task for creating a uniform spherical mesh with a given resolution
    """

    def __init__(self, component, resolution, icosahedral):
        """
        Create the base mesh task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution in km of the mesh

        icosahedral : bool
            Whether the mesh is a subdivided icosahedral mesh, as opposed to
            a quasi-uniform mesh
        """
        base_mesh_step, _ = add_uniform_spherical_base_mesh_step(
            resolution=resolution,
            icosahedral=icosahedral,
        )

        # We will take the unusual step of putting the task in a subdirectory
        # of the step because most folks will just run the step directly
        subdir = os.path.join(base_mesh_step.subdir, 'task')
        name = f'{base_mesh_step.name}_task'
        super().__init__(component=component, name=name, subdir=subdir)

        self.set_shared_config(
            config=base_mesh_step.config, link=f'{base_mesh_step.name}.cfg'
        )
        self.add_step(base_mesh_step)
