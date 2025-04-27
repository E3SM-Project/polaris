from typing import List

from polaris import Component

# import new components here
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.add_tasks import add_e3sm_init_tasks
from polaris.tasks.mesh import mesh
from polaris.tasks.mesh.add_tasks import add_mesh_tasks
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.add_tasks import add_ocean_tasks
from polaris.tasks.seaice import seaice
from polaris.tasks.seaice.add_tasks import add_seaice_tasks

# Add new components alphabetically to this list
_components: List[Component] = [
    e3sm_init,
    mesh,
    ocean,
    seaice,
]

_tasks_added = False


def get_components():
    """
    Add all tasks to the Polaris components
    """
    global _tasks_added
    if not _tasks_added:
        # add tasks to each component
        add_e3sm_init_tasks(component=e3sm_init)
        add_mesh_tasks(component=mesh)
        add_ocean_tasks(component=ocean)
        add_seaice_tasks(component=seaice)

        _tasks_added = True

    return _components
