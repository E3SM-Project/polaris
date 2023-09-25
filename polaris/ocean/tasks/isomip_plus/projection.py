import pyproj


def get_projection_string(lat0):
    """
    Get a stereographic projection string that should be used to define
    latitudes and longitudes for the ISOMIP+ x-y coordinates

    Parameters
    ----------
    lat0 : float
        The reference latitude at y=0

    Returns
    -------
    proj_str : str
        The projection string
    """
    proj_str = (f'+proj=stere +lon_0=0 +lat_0={lat0} +lat_ts={lat0} +x_0=0.0 '
                f'+y_0=0.0 +ellps=WGS84')
    return proj_str


def get_projections(lat0):
    """
    Get a stereographic and lat-lon projection that can be used to transform
    between lat-lon and ISOMIP+ x-y coordinates

    Parameters
    ----------
    lat0 : float
        The reference latitude at y=0

    Returns
    -------
    projection : pyproj.Proj
        The stereographic projection

    lat_lon_projection : pyproj.Proj
        The lat-lon projection
    """
    projection = pyproj.Proj(get_projection_string(lat0))
    lat_lon_projection = pyproj.Proj(proj='latlong', datum='WGS84')

    return projection, lat_lon_projection
