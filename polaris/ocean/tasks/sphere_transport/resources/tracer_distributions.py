import numpy as np
from mpas_tools.transects import lon_lat_to_cartesian
from mpas_tools.vector import Vector


def slotted_cylinders(lon, lat, r, b, c, sphere_radius):
    """
    Compute two slotted cylinders on the sphere
    Lauritzen et al. 2012 eqn. (12)

    Parameters
    ----------
    lon : np.ndarray of type float
        longitude of cells on the sphere

    lat : np.ndarray of type float
        latitude of cells on the sphere

    r : float
        radius of each slotted cylinder

    b : float
        background value of the tracer

    c : float
        value of each slotted cylinder

    sphere_radius : float
        radius of the sphere

    Returns
    -------
    scs : np.ndarray
        slotted cylinder tracer values
    """
    lon_thr = 1 / (6 * 2)
    lat_thr = 5 / (12 * 2)
    lon1 = 5 * (np.pi / 6)
    lat1 = 0
    lon2 = -5 * (np.pi / 6)
    lat2 = 0
    lon0 = np.where(lon > np.pi,
                    lon - 2 * np.pi,
                    lon)
    x, y, z = lon_lat_to_cartesian(lon, lat, sphere_radius, degrees=False)
    x1, y1, z1 = lon_lat_to_cartesian(lon1, lat1, sphere_radius, degrees=False)
    x2, y2, z2 = lon_lat_to_cartesian(lon2, lat2, sphere_radius, degrees=False)
    xyz = Vector(x, y, z)
    xyz1 = Vector(x1, y1, z1)
    xyz2 = Vector(x2, y2, z2)
    r1 = xyz.angular_distance(xyz1)
    r2 = xyz.angular_distance(xyz2)
    scs = np.where(r1 <= r,
                   np.where(np.logical_or((abs(lon0 - lon1) >= lon_thr),
                                          np.logical_and(
                                              abs(lon0 - lon1) < lon_thr,
                                              lat - lat1 < -lat_thr)),
                            c,
                            b),
                   np.where(np.logical_and(r2 <= r,
                                           np.logical_or(
                                               (abs(lon0 - lon2) >= lon_thr),
                                               np.logical_and(
                                                   abs(lon0 - lon2) < lon_thr,
                                                   lat - lat2 > lat_thr))),
                            c,
                            b))
    return scs


def cosine_bells(lon, lat, r, b, c, sphere_radius):
    """
    Compute two cosine bells on the sphere
    Lauritzen et al. 2012 eqn. (11)

    Parameters
    ----------
    lon : np.ndarray of type float
        longitude of cells on the sphere

    lat : np.ndarray of type float
        latitude of cells on the sphere

    r : float
        radius of each cosine bell

    b : float
        background value of the tracer

    c : float
        maximum value of each cosine bell

    sphere_radius : float
        radius of the sphere

    Returns
    -------
    cbs : np.ndarray
        cosine bell tracer values
    """
    # Location of the center of the first cosine bell
    lon1 = 5 * (np.pi / 6)
    lat1 = 0

    # Location of the center of the second cosine bell
    lon2 = -5 * (np.pi / 6)
    lat2 = 0

    x, y, z = lon_lat_to_cartesian(lon, lat, sphere_radius, degrees=False)
    x1, y1, z1 = lon_lat_to_cartesian(lon1, lat1, sphere_radius, degrees=False)
    x2, y2, z2 = lon_lat_to_cartesian(lon2, lat2, sphere_radius, degrees=False)
    xyz = Vector(x, y, z)
    xyz1 = Vector(x1, y1, z1)
    xyz2 = Vector(x2, y2, z2)
    # Distance of each cell from the center of the first cosine bell
    r1 = xyz.angular_distance(xyz1)
    # Distance of each cell from the center of the second cosine bell
    r2 = xyz.angular_distance(xyz2)

    cbs = np.where(r1 < r,
                   cosine_bell(1.0, r1, r),
                   np.where(r2 < r,
                            cosine_bell(1.0, r2, r),
                            0.))
    return b + c * cbs


def xyztrig(lon, lat, sphere_radius):
    """
    Compute C-infinity tracer (not included in Lauritzen et al. 2012)

    Parameters
    ----------
    lon : np.ndarray of type float
        longitude of cells on the sphere

    lat : np.ndarray of type float
        latitude of cells on the sphere

    r : float
        radius of each cosine bell

    b : float
        background value of the tracer

    c : float
        maximum value of each cosine bell

    sphere_radius : float
        radius of the sphere

    Returns
    -------
    f : np.ndarray
        C-infinity tracer values
    """
    x, y, z = lon_lat_to_cartesian(lon, lat, sphere_radius, degrees=False)
    x = np.divide(x, sphere_radius)
    y = np.divide(y, sphere_radius)
    z = np.divide(z, sphere_radius)
    f = 0.5 * (1 + np.sin(np.pi * x) * np.sin(np.pi * y) * np.sin(np.pi * z))
    return f


def cosine_bell(max_value, ri, r):
    """
    Compute values according to cosine bell function
    Lauritzen et al. 2012 eqn. (10)

    Parameters
    ----------
    max_value : float
        Maximum value of the cosine bell function

    ri : np.ndarray of type float
        Distance from the center of the cosine bell in meters

    r : float
        Radius of the cosine bell in meters

    Returns
    -------
    f : np.ndarray of type float
        Cosine bell tracer values
    """
    return max_value / 2.0 * (1.0 + np.cos(np.pi * np.divide(ri, r)))


def correlation_fn(q1, a, b, c):
    """
    Compute a quadratic function for nonlinear tracer correlation following
    Lauritzen et al. 2012 eqns. (14) and (15)

    Parameters
    ----------
    q1 : np.ndarray
        tracer values

    a : float
       quadratic coefficient

    b : float
       linear coefficient

    c : float
       offset

    Returns
    -------
    q2 : np.ndarray
        correlated tracer values
    """
    return a * q1**2. + b * q1 + c
