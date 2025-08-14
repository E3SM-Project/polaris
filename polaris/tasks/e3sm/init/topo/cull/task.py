import os

from polaris.task import Task
from polaris.tasks.e3sm.init.topo.cull.steps import (
    get_default_cull_topo_steps,
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
        base_mesh_step,
        combine_topo_step,
        remap_mask_step,
        unsmoothed_topo_step,
        include_viz=False,
    ):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The base mesh step containing input files to this step

        combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
            The step for combining global and Antarctic topography on a cubed
            sphere grid

        unsmoothed_topo_step : polaris.tasks.e3sm.init.topo.remap.RemapTopoStep
            The step for remapping the unsmoothed topography

        low_res : bool
            Whether the base mesh is low resolution (120km or coarser), so that
            a set of config options for low resolution and a lower resolution
            source topography should be used

        smoothing : bool, optional
            Whether to create a step with smoothing in addition to the step
            without smoothing

        include_viz : bool, optional
            Whether to include visualization steps
        """
        mesh_name = base_mesh_step.mesh_name
        subdir = os.path.join(mesh_name, 'topo', 'cull')
        super().__init__(
            component=component,
            name=f'{mesh_name}_cull_topo_task',
            subdir=subdir,
        )
        self.add_step(base_mesh_step, symlink='base_mesh')
        self.add_step(combine_topo_step, symlink='combine_topo')
        self.add_step(remap_mask_step, symlink='remap_mask')
        self.add_step(unsmoothed_topo_step, symlink='remap_unsmoothed_topo')
        steps, config = get_default_cull_topo_steps(
            component=component,
            base_mesh_step=base_mesh_step,
            unsmoothed_topo_step=unsmoothed_topo_step,
            include_viz=include_viz,
        )
        self.set_shared_config(config, link='cull_topo.cfg')
        for step in steps:
            self.add_step(step)

        self.combine_topo_step = combine_topo_step

    def configure(self):
        """
        Set the combine_topo_step to be cached
        """
        super().configure()
        # The combine topo step is really expensive so we want to use the
        # cached version
        self.combine_topo_step.cached = True
