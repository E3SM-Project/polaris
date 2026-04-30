from polaris.mesh.spherical.unified import LAT_LON_TARGET_GRID_RESOLUTIONS
from polaris.tasks.mesh.spherical.unified.coastline.task import (
    LatLonCoastlineTask,
)


def add_coastline_tasks(component):
    """
    Add standalone coastline tasks for each supported lat-lon target grid.

    Parameters
    ----------
    component : polaris.Component
        The mesh component that the tasks belong to
    """
    for resolution in LAT_LON_TARGET_GRID_RESOLUTIONS:
        component.add_task(
            LatLonCoastlineTask(component=component, resolution=resolution)
        )
