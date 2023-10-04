import numpy as np
from numpy import cos, pi, sin

from polaris.ocean.tasks.sphere_transport.resources.utils import (
    calc_local_east_north,
    lonlat2xyz,
)


def flow_nondivergent(t, lon, lat, u_0, tau):
    """
    Compute a nondivergent velocity field

    Parameters
    ----------
    t : np.ndarray of type float
        times in seconds at which to compute the velocity field

    lon : np.ndarray of type float
        longitude

    lat : np.ndarray of type float
        latitude

    u_0 : float
        velocity amplitude in meters per second

    tau : float
        time in seconds for the flow to circumnavigate the sphere

    Returns
    -------
    u : np.ndarray of type float
       zonal velocity

    v : np.ndarray of type float
       meridional velocity
    """
    lon_p = lon - 2. * pi * t / tau
    coslat = cos(lat)
    cost = cos(pi * t / tau)
    u = (1 / tau) * (u_0 * (sin(lon_p)**2) * sin(2 * lat) * cost +
                     2. * pi * coslat)
    v = (u_0 / tau) * sin(2 * lon_p) * coslat * cost
    return u, v


def flow_divergent(t, lon, lat, u_0, tau):
    """
    Compute a nondivergent velocity field

    Parameters
    ----------
    t : np.ndarray of type float
        times in seconds at which to compute the velocity field

    lon : np.ndarray of type float
        longitude

    lat : np.ndarray of type float
        latitude

    u_0 : float
        velocity amplitude in meters per second

    tau : float
        time in seconds for the flow to circumnavigate the sphere

    Returns
    -------
    u : np.ndarray of type float
       zonal velocity

    v : np.ndarray of type float
       meridional velocity
    """
    lon_p = lon - 2. * pi * t / tau
    coslat = cos(lat)
    cost = cos(pi * t / tau)
    u = (1 / tau) * (-u_0 * (sin(lon_p / 2)**2) * sin(2 * lat) *
                     (coslat**2) * cost + 2. * pi * coslat)
    v = (u_0 / (2 * tau)) * sin(lon_p) * (coslat**3) * cost
    return u, v


def flow_rotation(lon, lat, omega, tau):
    """
    Compute a nondivergent velocity field

    Parameters
    ----------
    lon : np.ndarray of type float
        longitude

    lat : np.ndarray of type float
        latitude

    omega : np.ndarray of type float
        vector defining the axis of rotation of the flow in cartesian
        coordinates

    tau : float
        time in seconds for the flow to circumnavigate the sphere

    Returns
    -------
    u : np.ndarray of type float
       zonal velocity

    v : np.ndarray of type float
       meridional velocity
    """
    omega = (2. * pi / tau) * (omega / np.linalg.norm(omega))
    x, y, z = lonlat2xyz(lon, lat)
    xyz = np.stack((x, y, z), axis=1)
    vel = np.cross(omega, np.transpose(xyz), axis=0)
    east, north = calc_local_east_north(x, y, z)
    u = np.sum(vel * east, axis=0)
    v = np.sum(vel * north, axis=0)
    return u, v
