from polaris.constants import pcd

# Temporary dictionary of constants not yet available via PCD, only the ones
# we actually use for now.
CONSTANTS = {
    'seawater_specific_heat_capacity_reference': 3.996e3,  # J kg-1 K-1
    'seawater_density_reference': 1.026e3,  # kg m-3
}

CONVERSION_FACTORS = {
    'day_to_s': 86400.0,
}


def get_constant(name):
    """
    Get constants from the Physical Constants Dictionary (PCD) if available,
    otherwise from the temporary dictionary of constants.

    Parameters
    ----------
    name : str
        The name of the PCD constant to retrieve.

    Returns
    -------
    value : float
        The value of the constant.
    """

    value = pcd.get_constant(name)
    if value is None:
        if name in CONSTANTS:
            value = CONSTANTS[name]
        elif name in CONVERSION_FACTORS:
            value = CONVERSION_FACTORS[name]
        else:
            raise ValueError(
                f'Constant {name} not found in Physical Constants Dictionary '
                f'or temporary constants'
            )

    return value
