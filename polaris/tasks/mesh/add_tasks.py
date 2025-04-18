from polaris.tasks.mesh.base import add_base_mesh_tasks


def add_mesh_tasks(component):
    """
    Add all tasks to the mesh component

    component : polaris.Component
        the mesh component that the tasks will be added to
    """
    # add tasks alphabetically
    add_base_mesh_tasks(component=component)
