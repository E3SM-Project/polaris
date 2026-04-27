import numpy as np
from geometric_features import read_feature_collection
from mpas_tools.mesh.creation.signed_distance import (
    signed_distance_from_geojson,
)

from polaris.constants import get_constant


def build_southern_ocean_background(
    lat, lon, high_res_km, low_res_km, region_filename
):
    """
    Build a Southern Ocean background field on a regular lat-lon grid.
    """
    earth_radius = get_constant('mean_radius')
    fc = read_feature_collection(region_filename)

    so_signed_distance = signed_distance_from_geojson(
        fc, lon, lat, earth_radius, max_length=0.25
    )

    # Equivalent to 20 degrees latitude
    transition_width_m = 1600e3
    transition_start_m = 500e3

    weights = 0.5 * (
        1
        + np.tanh(
            (so_signed_distance - transition_start_m) / transition_width_m
        )
    )

    return high_res_km * (1 - weights) + low_res_km * weights
