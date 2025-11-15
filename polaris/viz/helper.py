import cartopy.crs as ccrs

projections = {
    'PlateCarree': ccrs.PlateCarree,
    'LambertCylindrical': ccrs.LambertCylindrical,
    'Mercator': ccrs.Mercator,
    'Miller': ccrs.Miller,
    'Robinson': ccrs.Robinson,
    'Stereographic': ccrs.Stereographic,
    'RotatedPole': ccrs.RotatedPole,
    'InterruptedGoodeHomolosine': ccrs.InterruptedGoodeHomolosine,
    'EckertI': ccrs.EckertI,
    'EckertII': ccrs.EckertII,
    'EckertIII': ccrs.EckertIII,
    'EckertIV': ccrs.EckertIV,
    'EckertV': ccrs.EckertV,
    'EckertVI': ccrs.EckertVI,
    'EqualEarth': ccrs.EqualEarth,
    'NorthPolarStereo': ccrs.NorthPolarStereo,
    'SouthPolarStereo': ccrs.SouthPolarStereo,
}

# indexed by mpas-ocean variable name in instantaneous output
viz_dict = {
    'bottomDepth': {'colormap': 'cmo.deep', 'units': r'm'},
    'layerThickness': {'colormap': 'cmo.thermal', 'units': r'm'},
    'temperature': {'colormap': 'cmo.thermal', 'units': r'$^{\circ}$C'},
    'salinity': {'colormap': 'cmo.haline', 'units': r'g/kg'},
    'density': {'colormap': 'cmo.dense', 'units': r'kg/m$^3$'},
    'ssh': {'colormap': 'cmo.delta', 'units': r'm'},
    'vertVelocityTop': {'colormap': 'cmo.balance', 'units': r'm/s'},
    'normalVelocity': {'colormap': 'cmo.balance', 'units': r'm/s'},
    'velocityZonal': {'colormap': 'cmo.balance', 'units': r'm/s'},
    'velocityMeridional': {'colormap': 'cmo.balance', 'units': r'm/s'},
    'landIceFraction': {'colormap': 'cmo.ice', 'units': r''},
    'seaIceFraction': {'colormap': 'cmo.ice', 'units': r''},
    'default': {'colormap': 'cmo.dense', 'units': r''},
}


def get_projection(name: str, **kwargs):
    """Return a Cartopy projection by string name."""
    if name not in projections:
        raise ValueError(
            f"Unknown projection '{name}'. Available: {list(projections)}"
        )
    return projections[name](**kwargs)


def get_viz_defaults():
    """
    Return the whole dictionary of MPAS variables and default viz properties
    """
    return viz_dict


def determine_time_variable(ds):
    """
    Identify the variable prefix and time variable for MPAS datasets
    """
    prefix = ''
    time_variable = None
    if 'timeSeriesStatsMonthly' in ds.keys():
        prefix = 'timeMonthly_avg_'
        time_variable = 'xtime_startMonthly'
    elif 'xtime' in ds.keys():
        time_variable = 'xtime'
    elif 'Time' in ds.keys():
        prefix = 'timeMonthly_avg_'
        time_variable = 'Time'
    return prefix, time_variable
