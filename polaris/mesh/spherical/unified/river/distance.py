import numpy as np

from polaris.constants import get_constant

EARTH_RADIUS = get_constant('mean_radius')


def haversine_distance(lon_a, lat_a, lon_b, lat_b):
    """
    Compute great-circle distance in meters.

    Parameters
    ----------
    lon_a : float or array-like
        Longitude of the first point(s) in degrees.
    lat_a : float or array-like
        Latitude of the first point(s) in degrees.
    lon_b : float or array-like
        Longitude of the second point(s) in degrees.
    lat_b : float or array-like
        Latitude of the second point(s) in degrees.

    Returns
    -------
    float or array-like
        Great-circle distance(s) in meters.
    """
    lon_a = np.deg2rad(lon_a)
    lat_a = np.deg2rad(lat_a)
    lon_b = np.deg2rad(lon_b)
    lat_b = np.deg2rad(lat_b)
    delta_lon = lon_b - lon_a
    delta_lat = lat_b - lat_a
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat_a) * np.cos(lat_b) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS * np.arcsin(np.sqrt(haversine))
