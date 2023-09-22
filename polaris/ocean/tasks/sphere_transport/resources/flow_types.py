import numpy as np
from numpy import cos, pi, sin

from polaris.ocean.tasks.sphere_transport.resources.utils import (
    calc_local_east_north,
    lonlat2xyz,
)


def flow_nondivergent(t, lon, lat):
    s_day = 3600. * 24.
    twelve_days = s_day * 12.
    lon_p = lon - 2. * pi * t / twelve_days
    coslat = cos(lat)
    cost = cos(pi * t / twelve_days)
    u = (1 / twelve_days) * (10 * (sin(lon_p)**2) * sin(2 * lat) * cost +
                             2. * pi * coslat)
    v = (10 / twelve_days) * sin(2 * lon_p) * coslat * cost
    return u, v


def flow_divergent(t, lon, lat):
    s_day = 3600. * 24.
    twelve_days = 12. * s_day
    lon_p = lon - 2. * pi * t / twelve_days
    coslat = cos(lat)
    cost = cos(pi * t / twelve_days)
    u = (1 / twelve_days) * (-5 * (sin(lon_p / 2)**2) * sin(2 * lat) *
                             (coslat**2) * cost + 2. * pi * coslat)
    v = (2.5 / twelve_days) * sin(lon_p) * (coslat**3) * cost
    return u, v


def flow_rotation(lon, lat):
    s_day = 3600. * 24.
    twelve_days = 12. * s_day
    Omega = np.array([0.2, 0.7, 1.0])  # Constant rotation vector
    Omega = (2. * pi / twelve_days) * (Omega / np.linalg.norm(Omega))
    x, y, z = lonlat2xyz(lon, lat)
    xyz = np.stack((x, y, z), axis=1)
    vel = np.cross(Omega, np.transpose(xyz), axis=0)
    east, north = calc_local_east_north(x, y, z)
    u = np.sum(vel * east, axis=0)
    v = np.sum(vel * north, axis=0)
    return u, v
