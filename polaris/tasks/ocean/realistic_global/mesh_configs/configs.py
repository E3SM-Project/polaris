"""
Per-mesh config overrides for ``realistic_global`` ocean tasks.

A ``realistic_global`` task is registered once per MPAS mesh, and some config
options need to differ from mesh to mesh (the vertical grid, the ocean-culled
cell count, and later forward-run options).  This package holds one optional
config file per mesh, named ``<mesh_name>.cfg``.

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

Most meshes have no config file here at all; they simply use the defaults from
the task's own config file.
"""

import importlib.resources as imp_res

from polaris.config import PolarisConfigParser

MESH_CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.mesh_configs'


def add_realistic_global_mesh_config(config, mesh_name):
    """
    Add per-mesh ``realistic_global`` config overrides for ``mesh_name``, if
    any exist.

    This must be called *after* the task's own config file has been added, so
    that the per-mesh options take precedence.  If the mesh has no config file
    in this package, the call is a no-op.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config to add the per-mesh options to, modified in place.

    mesh_name : str
        The name of the MPAS mesh (e.g. ``'qu240km'`` or ``'u.oi240.lr240'``).

    Returns
    -------
    bool
        Whether a config file was found and added for this mesh.
    """
    config_filename = _get_mesh_config_filename(mesh_name)
    if config_filename is None:
        return False

    config.add_from_package(MESH_CONFIG_PACKAGE, config_filename)
    return True


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
        The per-mesh config, or ``None`` if this mesh has no config file.
    """
    config_filename = _get_mesh_config_filename(mesh_name)
    if config_filename is None:
        return None

    config = PolarisConfigParser()
    config.add_from_package(MESH_CONFIG_PACKAGE, config_filename)
    config.combine()
    return config


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


def _get_mesh_config_filename(mesh_name):
    """
    Get the config filename for one mesh, or ``None`` if it does not exist.
    """
    config_filename = f'{mesh_name}.cfg'
    package_files = imp_res.files(MESH_CONFIG_PACKAGE)
    if not package_files.joinpath(config_filename).is_file():
        return None
    return config_filename
