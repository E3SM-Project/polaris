import importlib.resources as imp_res
from functools import cache

from ruamel.yaml import YAML


def get_mesh_variables(group: str) -> list[str]:
    """
    Get a group of MPAS mesh variables from ``polaris/mesh/variables.yaml``

    Parameters
    ----------
    group : str
        The name of the group, such as ``length_variables`` (horizontal
        coordinates and lengths) or ``area_variables`` (horizontal areas)

    Returns
    -------
    variables : list of str
        The names of the variables in the group
    """
    groups = _read_mesh_variables()
    if group not in groups:
        raise ValueError(
            f'Unknown mesh variable group {group!r}; expected one of '
            f'{", ".join(groups)}'
        )
    return list(groups[group])


@cache
def _read_mesh_variables() -> dict[str, list[str]]:
    """Read the groups of mesh variables, once"""
    text = imp_res.files('polaris.mesh').joinpath('variables.yaml').read_text()
    groups = YAML(typ='safe').load(text)
    return {key: list(value) for key, value in groups.items()}
