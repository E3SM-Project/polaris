from polaris.mesh.spherical.unified.configs import (
    UNIFIED_MESH_NAMES,
    get_unified_mesh_config,
)


def get_sizing_field_config(mesh_name, filepath=None):
    """
    Load one unified mesh config with sizing-field defaults.

    Parameters
    ----------
    mesh_name : str
        The name of the unified mesh; must be a member of
        :py:data:`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`

    filepath : str, optional
        The path to the config file; passed directly to
        :py:func:`polaris.mesh.spherical.unified.get_unified_mesh_config`

    Returns
    -------
    config : polaris.config.PolarisConfigParser
        The merged config that combines the generic ``unified_mesh.cfg``
        defaults, the shared sizing-field defaults, and the named-mesh
        config file

    Raises
    ------
    ValueError
        If ``mesh_name`` is not a recognized unified mesh name
    """
    if mesh_name not in UNIFIED_MESH_NAMES:
        valid_mesh_names = ', '.join(UNIFIED_MESH_NAMES)
        raise ValueError(
            f'Unexpected unified mesh {mesh_name!r}. Valid mesh names '
            f'are: {valid_mesh_names}'
        )

    return get_unified_mesh_config(mesh_name=mesh_name, filepath=filepath)
