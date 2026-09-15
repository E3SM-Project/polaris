"""
The ``[ocean_analysis_ohc]`` config options, read in one place.

Both products that integrate heat content -- the maps, from a climatology,
and the time series, from a month at a time -- need the same elevation ranges
and the same specific heat capacity, so neither reads the section itself.
"""

from polaris.constants import get_constant
from polaris.ocean.vertical.elevation import parse_vertical_reduction

SECTION = 'ocean_analysis_ohc'


def get_elevation_ranges(config):
    """
    Get the elevation ranges heat content is integrated over

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    Returns
    -------
    ranges : list of polaris.ocean.vertical.elevation.VerticalReduction
        The parsed ranges, in the order they were requested

    Raises
    ------
    ValueError
        If an entry is not an elevation range
    """
    ranges = []
    for spec in config.getlist(SECTION, 'elevation_ranges'):
        reduction = parse_vertical_reduction(spec)
        if reduction.kind != 'range':
            raise ValueError(
                f'"{spec}" in [{SECTION}] elevation_ranges is not an '
                f'elevation range.  A range is given as <top>:<bottom> in m, '
                f'positive up, e.g. top:-700.0.  A single elevation belongs '
                f'in [ocean_analysis_climatology] elevations instead.'
            )
        ranges.append(reduction)
    return ranges


def get_specific_heat(config):
    """
    Get the specific heat capacity used to convert conservative temperature
    to heat content

    It defaults to the value in the Physical Constants Dictionary, which is
    what the rest of E3SM uses, and is a config option so that a user can try
    the TEOS-10 constant -- 0.1% higher, and the one with which the integral
    is heat content by definition rather than to that accuracy -- without a
    code change.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    Returns
    -------
    specific_heat : float
        The specific heat capacity of seawater in J kg-1 K-1
    """
    option = 'seawater_specific_heat_capacity'
    if config.has_option(SECTION, option):
        return config.getfloat(SECTION, option)
    return get_constant('seawater_specific_heat_capacity_reference')
