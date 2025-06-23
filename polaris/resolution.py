def resolution_to_string(resolution):
    """
    Convert a resolution to a subdirectory name (e.g. '240km', '30m', '0.1cm')

    Parameters
    ----------
    resolution : float
        The resolution in km

    Returns
    -------
    res_str : str
        The resolution as a string for use as a subdirectory

    """
    res_str, units = resolution_to_string_and_units(resolution)
    res_str = f'{res_str}{units}'
    return res_str


def resolution_to_string_and_units(resolution):
    """
    Convert a resolution to a string and its units

    Parameters
    ----------
    resolution : float
        The resolution in km

    Returns
    -------
    res_str : str
        The resolution as a string for use as a subdirectory

    units : str
        The units of the resolution (e.g. 'km', 'm', 'cm')
    """
    if resolution >= 1.0:
        res_str = f'{resolution:g}'
        units = 'km'
    elif resolution < 0.001:
        res_str = f'{resolution * 1.0e5:g}'
        units = 'cm'
    else:
        res_str = f'{resolution * 1000.0:g}'
        units = 'm'
    return res_str, units
