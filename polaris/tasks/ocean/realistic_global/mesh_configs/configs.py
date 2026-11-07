"""
Per-mesh config overrides for ``realistic_global`` ocean tasks.

A ``realistic_global`` task is registered once per MPAS mesh, and some config
options need to differ from mesh to mesh (the vertical grid, the ocean-culled
cell count, and the resolution-dependent forward-run options).  This package
holds one optional config file per mesh, named ``<mesh_name>.cfg``.

These files are deliberately separate from the per-mesh configs in
``polaris.mesh.spherical.unified``.  The two are joined by the mesh name but
have different owners:

* ``polaris/mesh/spherical/unified/<mesh_name>.cfg`` (mesh component)
  describes the mesh itself: resolutions, river networks, sizing fields and
  the approximate total cell count.
* ``<mesh_name>.cfg`` in this package (ocean component) describes what the
  ocean does on that mesh: the vertical grid, the ocean-culled cell count and
  other ocean-specific options.

Options specific to the ocean belong here, not in the mesh component.

A simple base mesh with the same ocean resolution as a unified mesh -- its
unified twin, listed in ``UNIFIED_TWINS`` -- shares the twin's config file, and
the twin's dynamic-adjustment schedule, so the two are configured in one place.
A base mesh's own config file, if it has one, is added after its twin's.

Most other meshes have no config file here at all; they simply use the
defaults from the task's own config file.
"""

import importlib.resources as imp_res
from types import MappingProxyType

from polaris.config import PolarisConfigParser

MESH_CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.mesh_configs'

#: The unified mesh whose ocean resolution each simple base mesh shares
UNIFIED_TWINS = MappingProxyType(
    {
        'icos240km': 'u-oi240-lr240',
        'qu240km': 'u-oi240-lr240',
        'qu30km': 'u-oi30-lr10',
        'so12to30km': 'u-oi-so12to30-lr10',
        'rrs6to18km': 'u-oi6to18-lr12p5',
    }
)


def add_realistic_global_mesh_config(config, mesh_name):
    """
    Add per-mesh ``realistic_global`` config overrides for ``mesh_name``, if
    any exist.

    This must be called *after* the task's own config file has been added, so
    that the per-mesh options take precedence.  The config file of the mesh's
    unified twin, if it has one, is added first, then the mesh's own.  If
    neither has a config file in this package, the call is a no-op.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config to add the per-mesh options to, modified in place.

    mesh_name : str
        The name of the MPAS mesh (e.g. ``'qu240km'`` or ``'u-oi240-lr240'``).

    Returns
    -------
    bool
        Whether a config file was found and added for this mesh.
    """
    config_filenames = _get_mesh_config_filenames(mesh_name)
    for config_filename in config_filenames:
        config.add_from_package(MESH_CONFIG_PACKAGE, config_filename)
    return len(config_filenames) > 0


def get_realistic_global_mesh_config(mesh_name):
    """
    Get a config containing only the per-mesh ``realistic_global`` options for
    ``mesh_name``.

    This is for callers that need a per-mesh option before a task config
    exists (e.g. sizing MPI resources at setup time).  Callers that already
    have the task config should read from it directly instead, so that user
    overrides are honored.

    Parameters
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    Returns
    -------
    polaris.config.PolarisConfigParser or None
        The per-mesh config, or ``None`` if neither this mesh nor its unified
        twin has a config file.
    """
    config = PolarisConfigParser()
    if not add_realistic_global_mesh_config(config, mesh_name):
        return None
    config.combine()
    return config


def get_unified_twin(mesh_name):
    """
    Get the unified mesh whose ocean resolution a simple base mesh shares.

    Parameters
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    Returns
    -------
    str or None
        The name of the unified twin, or ``None`` if the mesh has none.
    """
    return UNIFIED_TWINS.get(mesh_name)


def get_mesh_config_names():
    """
    Get the names of the meshes that have a config file in this package.

    Returns
    -------
    tuple of str
        The mesh names, sorted.
    """
    package_files = imp_res.files(MESH_CONFIG_PACKAGE)
    mesh_names = [
        resource.name[: -len('.cfg')]
        for resource in package_files.iterdir()
        if resource.is_file() and resource.name.endswith('.cfg')
    ]
    return tuple(sorted(mesh_names))


def _get_mesh_config_filenames(mesh_name):
    """
    Get the config filenames for one mesh that exist in this package: its
    unified twin's first, then its own.
    """
    package_files = imp_res.files(MESH_CONFIG_PACKAGE)
    mesh_names = [get_unified_twin(mesh_name), mesh_name]
    return [
        f'{name}.cfg'
        for name in mesh_names
        if name is not None and package_files.joinpath(f'{name}.cfg').is_file()
    ]
