import os

from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.task import Task
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_lat_lon_topo_steps,
)
from polaris.tasks.mesh.spherical.unified.coastline.steps import (
    get_lat_lon_coastline_steps,
)


class LatLonCoastlineTask(Task):
    """
    A task for preparing coastline products on a latitude-longitude grid.
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
            'lat_lon',
            resolution_name,
            'task',
        )
        super().__init__(
            component=component,
            name=f'coastline_lat_lon_{resolution_name}_task',
            subdir=subdir,
        )

        combine_steps, _ = get_lat_lon_topo_steps(
            component=e3sm_init,
            resolution=resolution,
            include_viz=False,
        )
        self.combine_topo_step = combine_steps[0]
        self.add_step(self.combine_topo_step, symlink='combine_topo')

        steps, config = get_lat_lon_coastline_steps(
            component=component,
            combine_topo_step=self.combine_topo_step,
            resolution=resolution,
            include_viz=True,
        )
        self.set_shared_config(config, link='coastline.cfg')
        for step in steps:
            symlink = os.path.basename(step.subdir)
            self.add_step(step, symlink=symlink)
