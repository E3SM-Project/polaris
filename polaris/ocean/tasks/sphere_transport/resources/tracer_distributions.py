import numpy as np

from polaris.ocean.tasks.sphere_transport.resources.utils import (
    cosine_bell,
    great_circle_dist_xyz,
    lonlat2xyz,
)


# Lauritzen et al. 2012 eqn. (12)
def slotted_cylinders(lon, lat):
    b = 0.1
    c = 1.
    R = 1.
    Rh = R / 2
    lon_thr = Rh / (6 * R)
    lat_thr = 5 * (Rh / (12 * R))
    lon1 = 5 * (np.pi / 6)
    lat1 = 0
    lon2 = -5 * (np.pi / 6)
    lat2 = 0
    x, y, z = lonlat2xyz(lon, lat)
    lon0 = np.where(lon > np.pi,
                    lon - 2 * np.pi,
                    lon)
    x1, y1, z1 = lonlat2xyz(lon1, lat1)
    x2, y2, z2 = lonlat2xyz(lon2, lat2)
    r1 = great_circle_dist_xyz(x, y, z, x1, y1, z1)
    r2 = great_circle_dist_xyz(x, y, z, x2, y2, z2)
    scs = np.where(r1 <= Rh,
                   np.where(np.logical_or((abs(lon0 - lon1) >= lon_thr),
                                          np.logical_and(
                                              abs(lon0 - lon1) < lon_thr,
                                              lat - lat1 < -lat_thr)),
                            c,
                            b),
                   np.where(np.logical_and(r2 <= Rh,
                                           np.logical_or(
                                               (abs(lon0 - lon2) >= lon_thr),
                                               np.logical_and(
                                                   abs(lon0 - lon2) < lon_thr,
                                                   lat - lat2 > lat_thr))),
                            c,
                            b))
    return scs


# Lauritzen et al. 2012 eqn. (11)
def cosine_bells(lon, lat):
    r = 0.5
    b = 0.1
    c = 0.9
    lon1 = 5 * (np.pi / 6)
    lat1 = 0
    lon2 = -5 * (np.pi / 6)
    lat2 = 0
    x, y, z = lonlat2xyz(lon, lat)
    x1, y1, z1 = lonlat2xyz(lon1, lat1)
    x2, y2, z2 = lonlat2xyz(lon2, lat2)
    # TODO compare with distance_from_center
    r1 = great_circle_dist_xyz(x, y, z, x1, y1, z1)
    r2 = great_circle_dist_xyz(x, y, z, x2, y2, z2)
    cbs = np.where(r1 < r,
                   cosine_bell(r1, r),
                   np.where(r2 < r,
                            cosine_bell(r2, r),
                            0.))
    return b + c * cbs
