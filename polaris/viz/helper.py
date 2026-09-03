import textwrap

import cartopy.crs as ccrs
from matplotlib.backends.backend_agg import FigureCanvasAgg

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
    'velocity': {'colormap': 'cmo.balance', 'units': r'm/s'},
    'ssh': {'colormap': 'cmo.delta', 'units': r'm'},
    'landIceFraction': {'colormap': 'cmo.ice', 'units': r''},
    'seaIceFraction': {'colormap': 'cmo.ice', 'units': r''},
    'default': {'colormap': 'cmo.dense', 'units': r''},
}
viz_dict['temperatureInteriorRestoringValue'] = viz_dict['temperature']
viz_dict['salinityInteriorRestoringValue'] = viz_dict['salinity']
viz_dict['vertVelocityTop'] = viz_dict['velocity']
viz_dict['normalVelocity'] = viz_dict['velocity']
viz_dict['velocityZonal'] = viz_dict['velocity']
viz_dict['velocityMeridional'] = viz_dict['velocity']


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
    if 'xtime_startMonthly' in ds.keys():
        prefix = 'timeMonthly_avg_'
        time_variable = 'xtime_startMonthly'
    elif 'xtime' in ds.keys():
        time_variable = 'xtime'
    elif 'Time' in ds.keys():
        prefix = 'timeMonthly_avg_'
        time_variable = 'Time'
    return prefix, time_variable


def add_fitted_suptitle(fig, title, y=None, min_fontsize=8.0):
    """
    Add a title to a figure, sized so that it fits across the figure

    A title wider than the figure runs off both ends of the canvas, and is
    simply cropped when the figure is saved at a fixed size.  What it loses is
    the part that distinguishes one plot from another --- the elevation range,
    the season, the years --- so the title is shrunk to fit, and wrapped onto a
    second line if shrinking alone is not enough.  Nothing is dropped.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to title

    title : str
        The title, which may be longer than the figure is wide

    y : float, optional
        Where to place the title in figure coordinates.  A wrapped title is
        placed by the layout engine instead, since a fixed position would put
        its second line over the axes.

    min_fontsize : float, optional
        The size below which the title is wrapped rather than shrunk further

    Returns
    -------
    text : matplotlib.text.Text
        The title that was added
    """
    # measuring rendered text needs a canvas that can produce a renderer; a
    # bare figure carries one that cannot, and savefig would attach an Agg
    # canvas anyway, so attaching it here changes nothing that is drawn
    if not hasattr(fig.canvas, 'get_renderer'):
        FigureCanvasAgg(fig)

    text = fig.suptitle(title, y=y) if y is not None else fig.suptitle(title)
    fontsize = text.get_fontsize()
    # leave a small margin so the title does not touch the figure edge
    limit = 0.96 * fig.get_size_inches()[0] * fig.dpi

    def too_wide():
        extent = text.get_window_extent(renderer=fig.canvas.get_renderer())
        return extent.width > limit

    while too_wide() and fontsize > min_fontsize:
        fontsize = max(min_fontsize, fontsize * 0.95)
        text.set_fontsize(fontsize)

    if too_wide():
        # shrinking hit the floor, so wrap instead, and let the layout engine
        # place a title that is now two lines tall
        halves = textwrap.wrap(title, width=max(len(title) // 2, 1))
        text.set_text('\n'.join(halves[:1] + [' '.join(halves[1:])]))
        text.set_position((text.get_position()[0], 1.0))
        text.set_verticalalignment('top')

    return text
