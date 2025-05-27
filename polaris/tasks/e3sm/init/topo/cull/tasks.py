from polaris.mesh.base import get_base_mesh_steps
from polaris.tasks.e3sm.init.topo.combine.steps import get_combine_topo_steps
from polaris.tasks.e3sm.init.topo.cull.task import CullTopoTask
from polaris.tasks.e3sm.init.topo.remap.steps import (
    get_default_remap_topo_steps,
)


def add_cull_topo_tasks(component):
    """
    Add a task to remap topography for each supported base mesh

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """

    combine_steps = {}
    for low_res in [False, True]:
        combine_topo_steps, _ = get_combine_topo_steps(
            component=component, low_res=low_res
        )
        combine_steps[low_res] = combine_topo_steps[0]

    base_mesh_steps = get_base_mesh_steps()

    for base_mesh_step in base_mesh_steps:
        res = base_mesh_step.cell_width
        low_res = res >= 120.0
        combine_topo_step = combine_steps[low_res]

        remap_topo_steps, _ = get_default_remap_topo_steps(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            low_res=low_res,
            smoothing=True,
            include_viz=False,
        )
        remap_mask_step = remap_topo_steps[0]
        unsmoothed_topo_step = remap_topo_steps[1]

        task = CullTopoTask(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            remap_mask_step=remap_mask_step,
            unsmoothed_topo_step=unsmoothed_topo_step,
            include_viz=True,
        )
        component.add_task(task)
