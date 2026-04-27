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
        base_mesh_steps=None,
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

        base_mesh_steps : list of polaris.Step, optional
            Steps needed to build the base mesh, including the base-mesh step
            itself. If omitted, only ``base_mesh_step`` is added to the task

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
        self._add_base_mesh_steps(
            base_mesh_step=base_mesh_step, base_mesh_steps=base_mesh_steps
        )
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
        for step in steps.values():
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

    def _add_base_mesh_steps(self, base_mesh_step, base_mesh_steps):
        """
        Add the base mesh and any steps required to build it.
        """
        if base_mesh_steps is None:
            base_mesh_steps = [base_mesh_step]

        for step in base_mesh_steps:
            if step is base_mesh_step:
                symlink = 'base_mesh'
            else:
                symlink = f'base_mesh_{step.name}'
            self.add_step(step, symlink=symlink)
