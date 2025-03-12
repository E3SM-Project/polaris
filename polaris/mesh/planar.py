import numpy as np


def compute_planar_hex_nx_ny(lx, ly, resolution):
    """
    Compute number of grid cells in each direction for the uniform, hexagonal
    planar mesh with the given physical sizes and resolution.  The resulting
    ``nx`` and ``ny`` account for the staggered nature of the hexagonal grid
    in the y direction, and are appropriate for passing to
    :py:func:`mpas_tools.planar_hex.make_planar_hex_mesh()`.

    Parameters
    ----------
    lx : float
        The size of the domain in km in the x direction

    ly : float
        The size of the domain in km in the y direction

    resolution : float
        The resolution of the mesh (distance between cell centers) in km

    Returns
    -------
    nx : int
        The number of grid cells in the x direction

    ny : int
        The number of grid cells in the y direction
    """
    # these could be hard-coded as functions of specific supported
    # resolutions but it is preferable to make them algorithmic like here
    # for greater flexibility
    nx = max(2 * int(0.5 * lx / resolution + 0.5), 4)
    # factor of 2/sqrt(3) because of hexagonal mesh
    ny = max(2 * int(0.5 * ly * (2.0 / np.sqrt(3)) / resolution + 0.5), 4)
    return nx, ny
