from polaris.e3sm.init.topo import (
    get_cubed_sphere_resolution,
    uses_low_res_cubed_sphere,
)
from polaris.mesh.base import get_base_mesh_steps
from polaris.tasks.e3sm.init.topo.combine import (
    get_cubed_sphere_topo_steps,
)
from polaris.tasks.e3sm.init.topo.remap import RemapTopoTask


def add_remap_topo_tasks(component):
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
        combine_steps[low_res] = combine_topo_steps[0]

    base_mesh_steps = get_base_mesh_steps()

    for base_mesh_step in base_mesh_steps:
        low_res = uses_low_res_cubed_sphere(base_mesh_step.cell_width)
        task = RemapTopoTask(
            component=component,
            base_mesh_step=base_mesh_step,
            combine_topo_step=combine_steps[low_res],
            low_res=low_res,
            smoothing=True,
            include_viz=True,
        )
        component.add_task(task)
