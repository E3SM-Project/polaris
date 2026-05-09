import os

from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.task import Task
from polaris.tasks.mesh.spherical.unified.coastline.steps import (
    get_unified_mesh_coastline_steps,
)


class LatLonCoastlineTask(Task):
    """
    A task for preparing coastline products on a latitude-longitude grid.

    At the finest supported resolution the task runs a full
    :class:`ComputeCoastlineStep`.  At coarser resolutions the task runs a
    :class:`RemapCoastlineStep` that remaps from the finest-resolution output,
    preserving the higher-fidelity coastline geometry.
    """

    def __init__(self, component, resolution):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        resolution : float
            The latitude-longitude resolution in degrees
        """
        resolution_name = format_lat_lon_resolution_name(resolution)
        subdir = os.path.join(
            'spherical',
            'unified',
            'coastline',
            resolution_name,
            'task',
        )
        super().__init__(
            component=component,
            name=f'coastline_lat_lon_{resolution_name}_task',
            subdir=subdir,
        )

        steps, config = get_unified_mesh_coastline_steps(
            resolution=resolution, include_viz=True
        )
        self.set_shared_config(config, link='coastline.cfg')
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
