import pyproj


def get_projection_string():
    """
    Get a stereographic projection string that should be used to define
    latitudes and longitudes for the ISOMIP+ x-y coordinates

    Returns
    -------
    proj_str : str
        The projection string
    """
    # y_0 is half way through the domain so the longitude is approximately
    # like -y
    #
    # x_0 is close to lat=-75 and lon=90 so latitude is approximately like x
    proj_str = (
        '+proj=stere +lon_0=0 +lat_0=-90 +lat_ts=-75.0 +x_0=-2000e3 '
        '+y_0=40.0e3 +ellps=WGS84'
    )
    return proj_str


def get_projections():
    """
    Get a stereographic and lat-lon projection that can be used to transform
    between lat-lon and ISOMIP+ x-y coordinates

    Returns
    -------
    projection : pyproj.Proj
        The stereographic projection

    lat_lon_projection : pyproj.Proj
        The lat-lon projection
    """
    projection = pyproj.Proj(get_projection_string())
    lat_lon_projection = pyproj.Proj(proj='latlong', datum='WGS84')

    return projection, lat_lon_projection
