from polaris.constants import pcd

# Dictionary of any constants not covered by PCD
CONSTANTS: dict[str, float] = {}

CONVERSION_FACTORS: dict[str, float] = {
    'day_to_s': 86400.0,
}


def get_constant(name: str) -> float:
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
