import os

from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.task import Task
from polaris.tasks.e3sm.init.topo.combine.files import ANTARCTIC
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_cubed_sphere_topo_steps,
    get_lat_lon_topo_steps,
)


class CubedSphereCombineTask(Task):
    """
    A task for creating combined topography on a cubed-sphere target grid.
    """

    def __init__(self, component, resolution, antarctic_dataset=ANTARCTIC):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        resolution : int
            The cubed-sphere resolution, such as 3000 or 120.

        antarctic_dataset : str, optional
            The Antarctic dataset, by default the one downstream tasks use.
        """
        resolution_name = f'ne{resolution}'
        name = (
            CombineStep.get_name(
                'cubed_sphere', resolution_name, antarctic_dataset
            )
            + '_task'
        )
        subdir = os.path.join(
            CombineStep.get_subdir(antarctic_dataset),
            'cubed_sphere',
            resolution_name,
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
            antarctic_dataset=antarctic_dataset,
        )
        self.set_shared_config(config, link='combine_topo.cfg')
        for step in steps.values():
            self.add_step(step)
            self.free_running_steps.add(step.subdir)


class LatLonCombineTask(Task):
    """
    A task for creating combined topography on a latitude-longitude grid.
    """

    def __init__(self, component, resolution, antarctic_dataset=ANTARCTIC):
        """
        Create a new task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        resolution : float
            The latitude-longitude resolution in degrees.

        antarctic_dataset : str, optional
            The Antarctic dataset, by default the one downstream tasks use.
        """
        resolution_name = format_lat_lon_resolution_name(resolution)
        subdir = os.path.join(
            CombineStep.get_subdir(antarctic_dataset),
            'lat_lon',
            resolution_name,
            'task',
        )
        super().__init__(
            component=component,
            name=(
                CombineStep.get_name(
                    'lat_lon', resolution_name, antarctic_dataset
                )
                + '_task'
            ),
            subdir=subdir,
        )
        steps, config = get_lat_lon_topo_steps(
            component=component,
            resolution=resolution,
            include_viz=True,
            antarctic_dataset=antarctic_dataset,
        )
        self.set_shared_config(config, link='combine_topo.cfg')
        for step in steps.values():
            self.add_step(step)
            self.free_running_steps.add(step.subdir)
