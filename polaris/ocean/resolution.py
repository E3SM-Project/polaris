def resolution_to_subdir(resolution):
    """
    Convert a resolution to a subdirectory name

    Parameters
    ----------
    resolution : float
        The resolution in km

    Returns
    -------
    res_str : str
        The resolution as a string for use as a subdirectory

    """
    if resolution >= 1.0:
        res_str = f'{resolution:g}km'
    elif resolution < 0.001:
        res_str = f'{resolution * 1.0e5:g}cm'
    else:
        res_str = f'{resolution * 1000.0:g}m'
    return res_str
