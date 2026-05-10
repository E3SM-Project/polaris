from types import MappingProxyType
from typing import NamedTuple, Optional

from polaris.resolution import (
    resolution_to_string,
    resolution_to_string_and_units,
)


class BaseMeshDefinition(NamedTuple):
    """
    Immutable metadata for one supported simple base mesh.
    """

    prefix: str
    min_res: float
    max_res: Optional[float] = None


def get_base_mesh_step_names():
    """
    Get the supported simple base-mesh names in registration order.

    Returns
    -------
    mesh_names : tuple of str
        The supported simple base-mesh names.
    """
    return tuple(BASE_MESH_DEFINITIONS)


def get_base_mesh_definition(mesh_name):
    """
    Get metadata for one supported simple base mesh.

    Parameters
    ----------
    mesh_name : str
        The name of the simple base mesh.

    Returns
    -------
    definition : BaseMeshDefinition
        The mesh metadata needed to rebuild the shared step.
    """
    if mesh_name not in BASE_MESH_DEFINITIONS:
        valid_mesh_names = ', '.join(get_base_mesh_step_names())
        raise ValueError(
            f'Unknown simple base mesh {mesh_name}. Valid mesh names are: '
            f'{valid_mesh_names}'
        )
    return BASE_MESH_DEFINITIONS[mesh_name]


def get_base_mesh_steps():
    """
    Get a list of supported base mesh steps from the mesh component

    Returns
    -------
    base_mesh_steps : list of polaris.mesh.spherical.BaseMeshStep
        All supported base mesh steps in the mesh component
    """
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.mesh.base.add import add_spherical_base_mesh_step

    base_mesh_steps = []
    for mesh_name in get_base_mesh_step_names():
        definition = get_base_mesh_definition(mesh_name)
        base_mesh_step, _ = add_spherical_base_mesh_step(
            prefix=definition.prefix,
            min_res=definition.min_res,
            max_res=definition.max_res,
        )
        base_mesh_steps.append(base_mesh_step)

    return base_mesh_steps


def add_spherical_base_mesh_step(
    prefix,
    min_res,
    max_res=None,
):
    """
    Add one supported spherical base mesh step to a component.

    This compatibility wrapper preserves the historic
    ``polaris.mesh.base.add_spherical_base_mesh_step`` API while importing
    the lower-level implementation lazily to avoid circular imports.
    """
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.mesh.base.add import (
        add_spherical_base_mesh_step as add_base_mesh_step,
    )

    return add_base_mesh_step(
        prefix=prefix,
        min_res=min_res,
        max_res=max_res,
    )


def parse_mesh_filepath(mesh_path):
    component = mesh_path.split('/')[0]
    database = '/'.join(mesh_path.split('/')[1:-1])
    mesh_name = mesh_path.split('/')[-1]
    return component, database, mesh_name


def _get_base_mesh_name(prefix, min_res, max_res=None):
    if max_res is None:
        res_str = resolution_to_string(min_res)
    else:
        min_str, min_units = resolution_to_string_and_units(min_res)
        max_str, max_units = resolution_to_string_and_units(max_res)
        if min_units == max_units:
            min_units = ''
        res_str = f'{min_str}{min_units}to{max_str}{max_units}'
    return f'{prefix}{res_str}'


def _get_base_mesh_definitions():
    uniform_res = {
        'icos': [480.0, 240.0, 120.0, 60.0, 30.0],
        'qu': [480.0, 240.0, 210.0, 180.0, 150.0, 120.0, 90.0, 60.0, 30.0],
    }

    variable_res = {
        'so': [(12.0, 30.0)],
        'rrs': [(6.0, 18.0)],
    }

    definitions = {}
    for prefix, uniform_res_list in uniform_res.items():
        for resolution in uniform_res_list:
            mesh_name = _get_base_mesh_name(prefix=prefix, min_res=resolution)
            definitions[mesh_name] = BaseMeshDefinition(
                prefix=prefix,
                min_res=resolution,
            )

    for prefix, variable_res_list in variable_res.items():
        for min_res, max_res in variable_res_list:
            mesh_name = _get_base_mesh_name(
                prefix=prefix,
                min_res=min_res,
                max_res=max_res,
            )
            definitions[mesh_name] = BaseMeshDefinition(
                prefix=prefix,
                min_res=min_res,
                max_res=max_res,
            )

    return definitions


BASE_MESH_DEFINITIONS = MappingProxyType(_get_base_mesh_definitions())
