from polaris.e3sm.init.topo import (
    CUBED_SPHERE_RESOLUTIONS,
    LAT_LON_RESOLUTIONS,
)
from polaris.tasks.e3sm.init.topo.combine.task import (
    CubedSphereCombineTask,
    LatLonCombineTask,
)


def add_combine_topo_tasks(component):
    """
    Add tasks for combining global and Antarctic topography datasets

    Parameters
    ----------
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
