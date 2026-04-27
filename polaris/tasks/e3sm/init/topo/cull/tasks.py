from polaris.e3sm.init.topo import (
    get_cubed_sphere_resolution,
    uses_low_res_cubed_sphere,
)
from polaris.mesh.base import get_base_mesh_steps
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.mesh.spherical.unified.base_mesh import (
    get_unified_finest_cell_width,
)
from polaris.tasks.e3sm.init.topo.combine import (
    get_cubed_sphere_topo_steps,
)
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.cull.task import CullTopoTask
from polaris.tasks.e3sm.init.topo.remap.steps import (
    get_default_remap_topo_steps,
)
from polaris.tasks.mesh.spherical.unified.base_mesh import (
    get_unified_base_mesh_steps,
)


def add_cull_topo_tasks(component):
    """
    Add a task to remap topography for each supported base mesh

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """

    combine_steps = {}
    for low_res in [False, True]:
        resolution = get_cubed_sphere_resolution(low_res)
        combine_topo_steps, _ = get_cubed_sphere_topo_steps(
            component=component, resolution=resolution
        )
        combine_steps[low_res] = combine_topo_steps[
            CombineStep.get_name('cubed_sphere', f'ne{resolution}')
        ]

    base_mesh_steps = get_base_mesh_steps()

    for base_mesh_step in base_mesh_steps:
        low_res = uses_low_res_cubed_sphere(base_mesh_step.cell_width)
        combine_topo_step = combine_steps[low_res]

        remap_topo_steps, _ = get_default_remap_topo_steps(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            low_res=low_res,
            smoothing=True,
            include_viz=False,
        )
        remap_mask_step = remap_topo_steps['mask_topo']
        unsmoothed_topo_step = remap_topo_steps['remap_unsmoothed']

        task = CullTopoTask(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            remap_mask_step=remap_mask_step,
            unsmoothed_topo_step=unsmoothed_topo_step,
            include_viz=True,
        )
        component.add_task(task)

    for mesh_name in UNIFIED_MESH_NAMES:
        unified_steps, unified_config = get_unified_base_mesh_steps(
            mesh_name=mesh_name,
            include_viz=False,
        )
        base_mesh_step = unified_steps['base_mesh']
        finest_cell_width = get_unified_finest_cell_width(unified_config)
        low_res = uses_low_res_cubed_sphere(finest_cell_width)
        combine_topo_step = combine_steps[low_res]

        remap_topo_steps, _ = get_default_remap_topo_steps(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            low_res=low_res,
            smoothing=True,
            include_viz=False,
        )
        remap_mask_step = remap_topo_steps['mask_topo']
        unsmoothed_topo_step = remap_topo_steps['remap_unsmoothed']

        task = CullTopoTask(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_topo_step,
            remap_mask_step=remap_mask_step,
            unsmoothed_topo_step=unsmoothed_topo_step,
            base_mesh_steps=list(unified_steps.values()),
            include_viz=True,
        )
        component.add_task(task)
