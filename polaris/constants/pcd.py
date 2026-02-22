import os
import warnings
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


def get_pcd_version():
    """
    Get the PCD version from Polaris' packaged ``pcd.yaml``.

    Returns
    -------
    version : str
        The PCD version.
    """
    return str(
        _get_version_from_pcd_dict(PCD_FULL, 'polaris.constants/pcd.yaml')
    )


def get_pcd_version_from_file(filename):
    """
    Get the PCD version from a ``pcd.yaml`` file.

    Parameters
    ----------
    filename : str
        The path to the PCD YAML file.

    Returns
    -------
    version : str
        The PCD version.
    """
    with open(filename, encoding='utf-8') as f:
        yaml_data = YAML(typ='rt')
        pcd_full = yaml_data.load(f.read())

    return str(_get_version_from_pcd_dict(pcd_full, filename))


def check_pcd_version_matches_branch(branch, model):
    """
    Check that the PCD version in Polaris matches the version in a branch.

    Parameters
    ----------
    branch : str
        The path to the base of an E3SM or Omega branch containing
        ``share/pcd.yaml``.

    model : str
        The model being set up (e.g. ``'mpas-ocean'`` or ``'omega'``).

    Raises
    ------
    ValueError
        If the PCD version in Polaris and the branch are not identical.
    """
    branch = os.path.abspath(branch)
    branch_pcd_path = os.path.join(branch, 'share', 'pcd.yaml')
    if not os.path.exists(branch_pcd_path):
        warnings.warn(
            f'Could not check PCD version for model {model} because '
            f'`share/pcd.yaml` was not found at {branch_pcd_path}. '
            f'Skipping PCD version check for this branch.',
            stacklevel=2,
        )
        return

    polaris_version = get_pcd_version()
    branch_version = get_pcd_version_from_file(branch_pcd_path)

    if polaris_version != branch_version:
        raise ValueError(
            f'PCD version mismatch for model {model}: Polaris has '
            f'{polaris_version} but branch {branch} has {branch_version}. '
            f'Please use matching PCD versions.'
        )


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


def _get_version_from_pcd_dict(pcd_full, source):
    """Get ``physical_constants_dictionary/version_number`` from YAML data."""
    if not isinstance(pcd_full, dict):
        raise ValueError(f'Invalid PCD format in {source}: expected a map.')

    if 'physical_constants_dictionary' not in pcd_full:
        raise ValueError(
            f'Invalid PCD format in {source}: missing '
            f'"physical_constants_dictionary".'
        )

    pcd_dict = pcd_full['physical_constants_dictionary']
    if not isinstance(pcd_dict, dict) or 'version_number' not in pcd_dict:
        raise ValueError(
            f'Invalid PCD format in {source}: missing '
            f'"physical_constants_dictionary/version_number".'
        )

    return pcd_dict['version_number']


# parsed full dictionary and constants for quick lookup
PCD_FULL, PCD_CONSTANTS = _parse_pcd()
