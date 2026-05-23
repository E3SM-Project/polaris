import os

from polaris.task import Task
from polaris.tasks.e3sm.init.topo.cull.steps import (
    get_cull_topo_steps,
)


class CullTopoTask(Task):
    """
    A task for culling a topography dataset to land and ocea regions (the
    latter both with and without ice-shelf cavities)

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
        include_viz=False,
    ):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        mesh_name : str
            The name of the base mesh to cull topography onto

        include_viz : bool, optional
            Whether to include visualization steps
        """
        subdir = os.path.join(mesh_name, 'topo', 'cull')
        super().__init__(
            component=component,
            name=f'{mesh_name}_cull_topo_task',
            subdir=subdir,
        )
        steps, config = get_cull_topo_steps(
            mesh_name=mesh_name,
            include_viz=include_viz,
        )
        self.set_shared_config(config, link='cull_topo.cfg')
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)
