import os

from polaris.task import Task
from polaris.tasks.e3sm.init.topo.remap.steps import (
    get_remap_topo_steps,
)


class RemapTopoTask(Task):
    """
    A task for remapping a topography dataset to a global MPAS mesh first
    without smoothing and then optionally with smoothing

    Attributes
    ----------
    combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
        The step for combining global and Antarctic topography on a cubed
        sphere grid
    """

    def __init__(
        self,
        component,
        mesh_name,
        smoothing=False,
        include_viz=False,
    ):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        mesh_name : str
            The name of the base mesh to remap topography onto

        smoothing : bool, optional
            Whether to create a step with smoothing in addition to the step
            without smoothing

        include_viz : bool, optional
            Whether to include visualization steps
        """
        subdir = os.path.join(mesh_name, 'topo', 'remap')
        super().__init__(
            component=component,
            name=f'{mesh_name}_topo_remap_task',
            subdir=subdir,
        )
        steps, config = get_remap_topo_steps(
            mesh_name=mesh_name,
            smoothing=smoothing,
            include_viz=include_viz,
        )
        self.set_shared_config(config, link='remap_topo.cfg')
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
