from importlib.resources import open_text

from ruamel.yaml import YAML


def get_constant(name):
    """
    Get a constant from the Physical Constants Dictionary (PCD).

    Parameters
    ----------
    name : str
        The name of the constant to retrieve.

    Returns
    -------
    value: float or None
        The value of the constant or None if not found.
    """
    return PCD_CONSTANTS.get(name, None)


def _parse_pcd():
    """Parse constants from the Physical Constants Dictonary (PCD) yaml file"""

    with open_text('polaris.constants', 'pcd.yaml') as f:
        yaml_data = YAML(typ='rt')
        pcd_full = yaml_data.load(f.read())

    pcd_constants = {}
    # constants are within the physical_constants_dictionary and set sections
    sets = pcd_full['physical_constants_dictionary']['set']
    # they may be within any of the available subsections
    for set_dict in sets:
        entries = next(iter(set_dict.values()))['entries']
        for entry in entries:
            name = entry['name']
            pcd_constants[name] = entry['value']

    return pcd_full, pcd_constants


# parsed full dictionary and constants for quick lookup
PCD_FULL, PCD_CONSTANTS = _parse_pcd()
