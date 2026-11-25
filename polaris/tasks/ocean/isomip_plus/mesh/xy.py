import numpy as np
import pyproj

from polaris.tasks.ocean.isomip_plus.projection import get_projections


def add_isomip_plus_xy(ds):
    """
    Add ISOMIP+ x and y coordinates to a mesh from a stereographic
    projection of its latitude and longitude

    Parameters
    ----------
    ds : xarray.Dataset
        The MPAS mesh with latitude and longitude
    """
    projection, lat_lon_projection = get_projections()
    transformer = pyproj.Transformer.from_proj(lat_lon_projection, projection)
    lon = np.rad2deg(ds.lonCell.values)
    lat = np.rad2deg(ds.latCell.values)

    x, y = transformer.transform(lon, lat)

    ds['xIsomipCell'] = ('nCells', x)
    ds['yIsomipCell'] = ('nCells', y)

    lon = np.rad2deg(ds.lonVertex.values)
    lat = np.rad2deg(ds.latVertex.values)

    x, y = transformer.transform(lon, lat)

    ds['xIsomipVertex'] = ('nVertices', x)
    ds['yIsomipVertex'] = ('nVertices', y)
