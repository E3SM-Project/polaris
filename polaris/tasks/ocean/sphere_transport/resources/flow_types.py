import numpy as np
import xarray as xr
from mpas_tools.transects import lon_lat_to_cartesian
from numpy import cos, pi, sin

from polaris.mesh.spherical import (
    calc_vector_east_north,
)


def flow_nondivergent(t, lon, lat, u_0, tau, sphere_radius):
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
    lon_p = lon - 2.0 * pi * t / tau
    coslat = cos(lat)
    cost = cos(pi * t / tau)
    u = (u_0 * sphere_radius / tau) * (
        (sin(lon_p) ** 2) * sin(2 * lat) * cost + 2.0 * pi * coslat
    )
    v = (u_0 * sphere_radius / tau) * sin(2 * lon_p) * coslat * cost
    return u, v


def flow_divergent(t, lon, lat, u_0, tau, sphere_radius):
    """
    Compute a divergent velocity field

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
    lon_p = lon - 2.0 * pi * t / tau
    coslat = cos(lat)
    cost = cos(pi * t / tau)
    u = (u_0 * sphere_radius / tau) * (
        -(sin(lon_p / 2) ** 2) * sin(2 * lat) * (coslat**2) * cost
        + 2.0 * pi * coslat
    )
    v = (u_0 * sphere_radius / (2 * tau)) * (
        sin(lon_p) * (coslat**3) * cost
    )
    return u, v


def flow_rotation(lon, lat, omega, tau, sphere_radius):
    """
    Compute a rotational velocity field

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

    sphere_radius : float
        radius of the sphere

    Returns
    -------
    u : np.ndarray of type float
       zonal velocity

    v : np.ndarray of type float
       meridional velocity
    """
    omega = (2.0 * pi / tau) * (omega / np.linalg.norm(omega))
    x, y, z = lon_lat_to_cartesian(lon, lat, sphere_radius, degrees=False)
    xyz = np.stack((x, y, z), axis=1)
    vel = np.cross(omega, np.transpose(xyz), axis=0)
    east, north = calc_vector_east_north(x, y, z)
    u = np.sum(vel * east, axis=0)
    v = np.sum(vel * north, axis=0)
    return u, v


def normal_velocity_from_zonal_meridional(
    ds_mesh, u, v, recompute_angle_edge=False
):
    """
    Compute normal velocity from zonal and meridional velocity components
    defined on edges
    """
    if recompute_angle_edge:
        angle_edge = recompute_angle_edge(ds_mesh)
    else:
        angle_edge = ds_mesh.angleEdge

    normal_velocity = xr.zeros_like(angle_edge)
    normal_velocity.values = u * np.cos(angle_edge) + v * np.sin(angle_edge)
    return normal_velocity
