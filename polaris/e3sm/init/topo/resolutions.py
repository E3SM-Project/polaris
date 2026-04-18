"""
Shared resolution definitions for e3sm/init topography workflows.
"""

STANDARD_CUBED_SPHERE_RESOLUTION = 3000
LOW_RES_CUBED_SPHERE_RESOLUTION = 120
LOW_RES_BASE_MESH_CELL_WIDTH = 120.0
LAT_LON_RESOLUTION_DECIMALS = 5

CUBED_SPHERE_RESOLUTIONS = (
    STANDARD_CUBED_SPHERE_RESOLUTION,
    LOW_RES_CUBED_SPHERE_RESOLUTION,
)

LAT_LON_RESOLUTIONS = (1.0, 0.25, 0.125, 0.0625, 0.03125)


def format_lat_lon_resolution_name(resolution):
    """
    Format a latitude-longitude resolution for use in task subdirectories.

    Parameters
    ----------
    resolution : float
        The latitude-longitude resolution in degrees.

    Returns
    -------
    resolution_name : str
        The formatted resolution name.
    """
    return f'{float(resolution):.{LAT_LON_RESOLUTION_DECIMALS}f}_degree'


def get_cubed_sphere_resolution(low_res):
    """
    Get the cubed-sphere source-topography resolution for a mode.

    Parameters
    ----------
    low_res : bool
        Whether the lower-resolution cubed-sphere product should be used.

    Returns
    -------
    resolution : int
        The cubed-sphere resolution.
    """
    if low_res:
        return LOW_RES_CUBED_SPHERE_RESOLUTION

    return STANDARD_CUBED_SPHERE_RESOLUTION


def uses_low_res_cubed_sphere(cell_width):
    """
    Determine whether a base mesh should use lower-resolution topography.

    Parameters
    ----------
    cell_width : float or None
        The representative base-mesh cell width in km.

    Returns
    -------
    low_res : bool
        Whether to use the lower-resolution cubed-sphere source topography.
    """
    return (
        cell_width is not None and cell_width >= LOW_RES_BASE_MESH_CELL_WIDTH
    )
