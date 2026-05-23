from polaris.mesh.base import (
    get_base_mesh_definition,
    get_base_mesh_step_names,
)
from polaris.mesh.base.add import add_spherical_base_mesh_step
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.base_mesh.steps import (
    get_unified_base_mesh_steps,
)


def get_base_mesh_steps(mesh_name, include_viz=False):
    """
    Get shared steps for building one named base mesh.

    Parameters
    ----------
    mesh_name : str
        The name of the simple or unified mesh.

    include_viz : bool, optional
        Whether to include visualization steps. This is currently a no-op
        for simple meshes.

    Returns
    -------
    steps : dict of str to polaris.Step
        All steps needed to build the base mesh, keyed by logical step
        name.

    config : polaris.config.PolarisConfigParser
        The shared config options for the named base mesh.
    """
    _validate_mesh_names()

    if mesh_name in get_base_mesh_step_names():
        return _get_simple_base_mesh_steps(
            mesh_name=mesh_name,
            include_viz=include_viz,
        )

    if mesh_name in UNIFIED_MESH_NAMES:
        return get_unified_base_mesh_steps(
            mesh_name=mesh_name, include_viz=include_viz
        )

    valid_mesh_names = ', '.join(
        list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    )
    raise ValueError(
        f'Unknown base mesh {mesh_name}. Valid mesh names are: '
        f'{valid_mesh_names}'
    )


def _get_simple_base_mesh_steps(mesh_name, include_viz=False):
    # Simple base meshes are always owned by the mesh component and do not
    # currently have optional visualization steps.
    del include_viz

    definition = get_base_mesh_definition(mesh_name)
    base_mesh_step, _ = add_spherical_base_mesh_step(
        prefix=definition.prefix,
        min_res=definition.min_res,
        max_res=definition.max_res,
    )
    return {'base_mesh': base_mesh_step}, base_mesh_step.config


def _validate_mesh_names():
    overlap = set(get_base_mesh_step_names()).intersection(UNIFIED_MESH_NAMES)
    if overlap:
        overlap_str = ', '.join(sorted(overlap))
        raise ValueError(
            f'Simple and unified mesh names must be disjoint. Overlap: '
            f'{overlap_str}'
        )
