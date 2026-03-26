import os

from polaris.task import Task
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_cubed_sphere_topo_steps,
    get_lat_lon_topo_steps,
)


class CubedSphereCombineTask(Task):
    """
    A task for creating combined topography on a cubed-sphere target grid.
    """

    def __init__(self, component, resolution):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        resolution : int
            The cubed-sphere resolution, such as 3000 or 120.
        """
        antarctic_dataset = CombineStep.ANTARCTIC
        global_dataset = CombineStep.GLOBAL
        name = (
            f'combine_topo_{antarctic_dataset}_{global_dataset}_'
            f'cubed_sphere_ne{resolution}_task'
        )
        subdir = os.path.join(
            CombineStep.get_subdir(),
            'cubed_sphere',
            f'ne{resolution}',
            'task',
        )
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
        )
        steps, config = get_cubed_sphere_topo_steps(
            component=component,
            resolution=resolution,
            include_viz=True,
        )
        self.set_shared_config(config, link='combine_topo.cfg')
        for step in steps:
            self.add_step(step)


class LatLonCombineTask(Task):
    """
    A task for creating combined topography on a latitude-longitude grid.
    """

    def __init__(self, component, resolution):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        resolution : float
            The latitude-longitude resolution in degrees.
        """
        resolution_name = f'{resolution:.4f}_degree'
        subdir = os.path.join(
            CombineStep.get_subdir(),
            'lat_lon',
            resolution_name,
            'task',
        )
        super().__init__(
            component=component,
            name=f'combine_topo_lat_lon_{resolution_name}_task',
            subdir=subdir,
        )
        steps, config = get_lat_lon_topo_steps(
            component=component,
            resolution=resolution,
            include_viz=False,
        )
        self.set_shared_config(config, link='combine_topo.cfg')
        for step in steps:
            self.add_step(step)
