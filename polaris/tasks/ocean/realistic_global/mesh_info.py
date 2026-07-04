"""
Helpers for looking up properties of a realistic-global mesh from its name,
using the existing base- and unified-mesh definitions.  Kept in one place so
both the init steps (e.g. WOA23 remapping) and the forward step can size
resources and time steps consistently before the mesh file exists.
"""

from polaris.mesh.base import (
    BASE_MESH_DEFINITIONS,
    get_base_mesh_definition,
    get_base_mesh_step_names,
)
from polaris.mesh.spherical.unified import (
    UNIFIED_MESH_NAMES,
    get_unified_mesh_config,
)
from polaris.mesh.spherical.unified.base_mesh import (
    get_unified_finest_cell_width,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    get_realistic_global_mesh_config,
)


def min_res_for_mesh(mesh_name):
    """
    The mesh minimum resolution in km, from the existing mesh definitions.

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name.

    Returns
    -------
    float
        The minimum cell resolution in km.
    """
    if mesh_name in get_base_mesh_step_names():
        return get_base_mesh_definition(mesh_name).min_res
    return get_unified_finest_cell_width(get_unified_mesh_config(mesh_name))


def estimate_cell_count(mesh_name):
    """
    Return an approximate MPAS cell count for the given mesh name, or
    ``None`` if the count cannot be determined.

    For simple base meshes (icos / qu / rrs / so) the count is derived
    from the minimum cell resolution via the heuristic
    ``6e8 / min_res_km**2``.  For unified meshes it is read from the
    ``approximate_cell_count`` option in the ``[unified_mesh]`` section
    of the per-mesh config file.

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name as registered in :py:func:`get_base_mesh_step_names`
        or :py:data:`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`.

    Returns
    -------
    int or None
    """
    if mesh_name in BASE_MESH_DEFINITIONS:
        min_res = BASE_MESH_DEFINITIONS[mesh_name].min_res  # km
        return 6e8 / min_res**2

    if mesh_name in UNIFIED_MESH_NAMES:
        cfg = get_unified_mesh_config(mesh_name)
        return cfg.getint(
            'unified_mesh', 'approximate_cell_count', fallback=None
        )

    return None


def estimate_ocean_cell_count(mesh_name, config=None):
    """
    Return an approximate cell count for the ocean + sea-ice culled mesh that
    the ocean model actually runs, or ``None`` if it cannot be determined.

    This is the appropriate size for ocean-model resources, since the full mesh
    includes finer land and river-channel refinement that is culled away before
    the ocean model runs.  It is read from the ``culled_ocean_cell_count``
    option in the ``[realistic_global_mesh]`` section when set; otherwise it
    falls back to :py:func:`estimate_cell_count` (the full mesh estimate).

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name.

    config : polaris.config.PolarisConfigParser, optional
        A config that already includes the per-mesh options for ``mesh_name``.
        Callers that have one should pass it so that user overrides of
        ``culled_ocean_cell_count`` are honored.  If it is not given, the
        per-mesh config file is read directly from the package instead.

    Returns
    -------
    int or None
    """
    if config is None:
        config = get_realistic_global_mesh_config(mesh_name)

    if config is not None:
        count = config.getint(
            'realistic_global_mesh', 'culled_ocean_cell_count', fallback=None
        )
        if count is not None:
            return count

    return estimate_cell_count(mesh_name)
