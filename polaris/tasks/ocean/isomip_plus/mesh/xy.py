from typing import TYPE_CHECKING

from polaris.lazy import lazy_module
from polaris.tasks.ocean.isomip_plus.projection import get_projections

if TYPE_CHECKING:
    import numpy as np
    import pyproj
else:
    np = lazy_module('numpy')
    pyproj = lazy_module('pyproj')


def add_isomip_plus_xy(ds):
    """
    Add x and y coordinates from a stereographic projection to a mesh on a
    sphere

    Parameters
    ----------
    ds : xarray.Dataset
        The MPAS mesh on a sphere
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
