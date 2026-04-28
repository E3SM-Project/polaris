from polaris.mesh.spherical.unified.configs import (
    UNIFIED_MESH_NAMES,
    get_unified_mesh_config,
)


def get_sizing_field_config(mesh_name, filepath=None):
    """
    Load one unified mesh config with sizing-field defaults.
    """
    if mesh_name not in UNIFIED_MESH_NAMES:
        valid_mesh_names = ', '.join(UNIFIED_MESH_NAMES)
        raise ValueError(
            f'Unexpected unified mesh {mesh_name!r}. Valid mesh names '
            f'are: {valid_mesh_names}'
        )

    return get_unified_mesh_config(mesh_name=mesh_name, filepath=filepath)
