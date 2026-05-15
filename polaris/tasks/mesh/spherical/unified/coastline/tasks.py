from polaris.mesh.spherical.unified import LAT_LON_TARGET_GRID_RESOLUTIONS
from polaris.tasks.mesh.spherical.unified.coastline.task import (
    LatLonCoastlineTask,
)


def add_coastline_tasks(component):
    """
    Add standalone coastline tasks for each supported lat-lon target grid.

    The finest-resolution task is created first so that its shared
    ComputeCoastlineStep is available when the coarser-resolution tasks need
    to reference it for remapping.

    Parameters
    ----------
    component : polaris.Component
        The mesh component that the tasks belong to
    """
    resolutions = sorted(LAT_LON_TARGET_GRID_RESOLUTIONS)
    for resolution in resolutions:
        component.add_task(
            LatLonCoastlineTask(
                component=component,
                resolution=resolution,
            )
        )
