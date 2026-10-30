"""
The projection that gives the MISOMIP meshes latitude and longitude

The ISOMIP+ and MISMIP+ protocols use planar coordinates in which x points
north and y west.  A transverse Mercator projection on a sphere of E3SM's
radius puts the center of the ISOMIP+ box, x = 560 km and y = 40 km, at 75°S
on the prime meridian, which runs along x.
"""

import numpy as np
import pyproj
from mpas_tools.cime.constants import constants

#: E3SM's sphere radius in m
SPHERE_RADIUS = constants['SHR_CONST_REARTH']


def get_projection_string():
    """
    Get the projection from the protocols' planar coordinates to latitude
    and longitude

    Returns
    -------
    proj_str : str
        The projection string
    """
    return (
        f'+proj=tmerc +R={SPHERE_RADIUS:.0f} +lat_0=-75 +lon_0=0 +k_0=1 '
        '+x_0=-40000 +y_0=560000 +axis=nwu +units=m'
    )


def get_lat_lon(x, y):
    """
    Get latitude and longitude from the protocols' planar coordinates

    Parameters
    ----------
    x : numpy.ndarray
        The protocol's x coordinate, pointing north, in m

    y : numpy.ndarray
        The protocol's y coordinate, pointing west, in m

    Returns
    -------
    lat : numpy.ndarray
        Latitude in radians

    lon : numpy.ndarray
        Longitude in radians, between 0 and 2 pi
    """
    transformer = pyproj.Transformer.from_proj(
        pyproj.Proj(get_projection_string()),
        pyproj.Proj(f'+proj=longlat +R={SPHERE_RADIUS:.0f}'),
    )
    lon, lat = transformer.transform(np.asarray(x), np.asarray(y))
    lat = np.deg2rad(lat)
    lon = np.mod(np.deg2rad(lon), 2.0 * np.pi)
    return lat, lon


def add_lat_lon(ds_mesh):
    """
    Replace the latitude and longitude of a planar MPAS mesh's cells, edges
    and vertices with those of the projection

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh, with ``xCell``, ``yCell`` and so on in the protocols'
        coordinates.  It is modified in place.
    """
    locations = [
        ('Cell', 'nCells'),
        ('Edge', 'nEdges'),
        ('Vertex', 'nVertices'),
    ]
    for loc, dim in locations:
        lat, lon = get_lat_lon(
            ds_mesh[f'x{loc}'].values, ds_mesh[f'y{loc}'].values
        )
        ds_mesh[f'lat{loc}'] = (dim, lat)
        ds_mesh[f'lon{loc}'] = (dim, lon)
