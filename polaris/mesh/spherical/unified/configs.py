import importlib.resources as imp_res
import os

from polaris.config import PolarisConfigParser

PACKAGE = 'polaris.mesh.spherical.unified'
RIVER_CONFIG_PACKAGE = 'polaris.mesh.spherical.unified.river'
RIVER_CONFIG_FILENAME = 'river_network.cfg'
DEFAULT_CONFIG_FILENAME = 'unified_mesh.cfg'


def _discover_mesh_names():
    """
    Discover unified-mesh names from config files in the package.
    """
    package_files = imp_res.files(PACKAGE)
    mesh_names = []
    for resource in package_files.iterdir():
        if not resource.is_file() or not resource.name.endswith('.cfg'):
            continue
        if resource.name == DEFAULT_CONFIG_FILENAME:
            continue

        config = PolarisConfigParser()
        config.add_from_package(PACKAGE, resource.name)
        config.combine()
        combined = config.combined
        assert combined is not None
        if not combined.has_section('unified_mesh'):
            continue

        mesh_name = combined.get('unified_mesh', 'mesh_name')
        expected_name = os.path.splitext(resource.name)[0]
        if mesh_name != expected_name:
            raise ValueError(
                f'Unified-mesh config {resource.name!r} declares '
                f'mesh_name={mesh_name!r}, expected {expected_name!r}.'
            )

        mesh_names.append(mesh_name)

    return tuple(sorted(mesh_names))


UNIFIED_MESH_NAMES = _discover_mesh_names()


def get_unified_mesh_config(mesh_name, filepath=None):
    """
    Load default, generic river and per-mesh unified-mesh configs.
    """
    config_filename = _get_mesh_config_filename(mesh_name)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(PACKAGE, DEFAULT_CONFIG_FILENAME)
    config.add_from_package(RIVER_CONFIG_PACKAGE, RIVER_CONFIG_FILENAME)
    config.add_from_package(PACKAGE, config_filename)
    config.combine()
    return config


def _get_mesh_config_filename(mesh_name):
    """
    Get the config filename for one named unified mesh.
    """
    if mesh_name not in UNIFIED_MESH_NAMES:
        valid_mesh_names = ', '.join(UNIFIED_MESH_NAMES)
        raise ValueError(
            f'Unexpected unified mesh {mesh_name!r}. Valid mesh names '
            f'are: {valid_mesh_names}'
        )

    return f'{mesh_name}.cfg'
