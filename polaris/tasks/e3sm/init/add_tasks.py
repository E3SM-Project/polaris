from polaris.tasks.e3sm.init.topo import (
    CUBED_SPHERE_RESOLUTIONS,
    LAT_LON_RESOLUTIONS,
)
from polaris.tasks.e3sm.init.topo.combine import (
    CubedSphereCombineTask,
    LatLonCombineTask,
)
from polaris.tasks.e3sm.init.topo.cull import add_cull_topo_tasks
from polaris.tasks.e3sm.init.topo.remap import add_remap_topo_tasks


def add_e3sm_init_tasks(component):
    """
    Add all tasks to the e3sm/init component

    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    for cubed_sphere_res in CUBED_SPHERE_RESOLUTIONS:
        component.add_task(
            CubedSphereCombineTask(
                component=component, resolution=cubed_sphere_res
            )
        )
    for lat_lon_res in LAT_LON_RESOLUTIONS:
        component.add_task(
            LatLonCombineTask(component=component, resolution=lat_lon_res)
        )

    add_remap_topo_tasks(component=component)

    add_cull_topo_tasks(component=component)
