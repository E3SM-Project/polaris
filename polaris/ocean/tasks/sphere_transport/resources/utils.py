import numpy as np
from numpy import arctan2, cos, pi, sin, sqrt


def calc_local_east_north(x, y, z):
    axis = [0, 0, 1]
    xyz = np.stack((x, y, z), axis=1)
    east = np.cross(axis, np.transpose(xyz), axis=0)
    north = np.cross(np.transpose(xyz), east, axis=0)
    east = east / np.linalg.norm(east, axis=0)
    north = north / np.linalg.norm(north, axis=0)
    return east, north


# Lauritzen et al. 2012 does not have a global C-infty tracer; we add this one.
def xyztrig(lon, lat):
    x, y, z = lonlat2xyz(lon, lat)
    f = 0.5 * (1 + sin(pi * x) * sin(pi * y) * sin(pi * z))
    return f


# Lauritzen et al. 2012 eqn. (10)
# TODO edit so that it is flexible with cosine_bell task
def cosine_bell(ri, r):
    return 0.5 * (1 + cos(pi * ri / r))


#   Lauritzen et al. 2012 eqns. (14) and (15)
def correlation_fn(q1):
    q2 = -0.8 * q1**2. + 0.9
    return q2


def lonlat2xyz(lon, lat):
    x = cos(lon) * cos(lat)
    y = sin(lon) * cos(lat)
    z = sin(lat)
    return x, y, z


# TODO: Does this fn need radius, or is it always just used for arc length?
def great_circle_dist_xyz(xA, yA, zA, xB, yB, zB):
    cp1 = yA * zB - yB * zA
    cp2 = xB * zA - xA * zB
    cp3 = xA * yB - xB * yA
    cpnorm = sqrt(cp1 * cp1 + cp2 * cp2 + cp3 * cp3)
    dotprod = xA * xB + yA * yB + zA * zB
    dist = arctan2(cpnorm, dotprod)
    return dist
