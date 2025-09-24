import cartopy.crs as ccrs

projections = {
    'PlateCarree': ccrs.PlateCarree,
    'Mercator': ccrs.Mercator,
    'Orthographic': ccrs.Orthographic,
    'Mollweide': ccrs.Mollweide,
    'Robinson': ccrs.Robinson,
    'LambertConformal': ccrs.LambertConformal,
    'LambertCylindrical': ccrs.LambertCylindrical,
    'AlbersEqualArea': ccrs.AlbersEqualArea,
    'NorthPolarStereo': ccrs.NorthPolarStereo,
    'SouthPolarStereo': ccrs.SouthPolarStereo,
}


def get_projection(name: str, **kwargs):
    """Return a Cartopy projection by string name."""
    if name not in projections:
        raise ValueError(
            f"Unknown projection '{name}'. Available: {list(projections)}"
        )
    return projections[name](**kwargs)


def get_viz_defaults():
    # indexed by mpas-ocean variable name in instantaneous output
    viz_dict = {
        'temperature': {'colormap': 'cmo.thermal', 'units': r'$^{\circ}$C'},
        'salinity': {'colormap': 'cmo.haline', 'units': r'g/kg'},
        'density': {'colormap': 'cmo.dense', 'units': r'kg/m$^3$'},
        'ssh': {'colormap': 'cmo.delta', 'units': r'm'},
        'vertVelocityTop': {'colormap': 'cmo.balance', 'units': r'm/s'},
        'normalVelocity': {'colormap': 'cmo.balance', 'units': r'm/s'},
        'velocityZonal': {'colormap': 'cmo.balance', 'units': r'm/s'},
        'velocityMeridional': {'colormap': 'cmo.balance', 'units': r'm/s'},
        'default': {'colormap': 'cmo.balance', 'units': r''},
    }
    return viz_dict
