import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
    get_mesh_config_names,
    get_realistic_global_mesh_config,
)

# meshes that override the default vertical grid with a cheap, coarse one
COARSE_MESH_NAMES = ('qu240km', 'icos240km', 'u.oi240.lr240')


def _get_init_config(mesh_name):
    """
    Build a config the way ``_get_init_config`` in ``init/steps.py`` does.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'realistic_global_init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


# -----------------------------------------------------------------------
# config file discovery
# -----------------------------------------------------------------------


@pytest.mark.parametrize('mesh_name', get_mesh_config_names())
def test_config_files_are_named_for_real_meshes(mesh_name):
    """
    Each config file is named after a mesh that actually exists.

    A misnamed file (e.g. ``qu240.cfg`` rather than ``qu240km.cfg``) would
    otherwise be silently ignored, since a mesh without a config file is
    a valid, common case.
    """
    valid_mesh_names = set(get_base_mesh_step_names()) | set(
        UNIFIED_MESH_NAMES
    )
    assert mesh_name in valid_mesh_names


def test_get_config_returns_none_for_mesh_without_file():
    assert get_realistic_global_mesh_config('icos120km') is None


def test_get_config_returns_none_for_unknown_mesh():
    assert get_realistic_global_mesh_config('nonexistent_mesh_xyz') is None


def test_add_config_reports_whether_it_added_anything():
    config = PolarisConfigParser()
    assert add_realistic_global_mesh_config(config, 'qu240km')
    assert not add_realistic_global_mesh_config(config, 'icos120km')


# -----------------------------------------------------------------------
# vertical-grid overrides
# -----------------------------------------------------------------------


@pytest.mark.parametrize('mesh_name', COARSE_MESH_NAMES)
def test_coarse_meshes_override_vertical_grid(mesh_name):
    """The 240 km meshes use a cheap 16-level tanh_dz grid."""
    config = _get_init_config(mesh_name)
    section = config['vertical_grid']
    assert section.get('grid_type') == 'tanh_dz'
    assert section.getint('vert_levels') == 16
    assert section.getfloat('bottom_depth') == 3000.0
    assert section.getfloat('min_layer_thickness') == 3.0
    assert section.getfloat('max_layer_thickness') == 500.0


@pytest.mark.parametrize('mesh_name', COARSE_MESH_NAMES)
def test_overrides_do_not_replace_other_options(mesh_name):
    """
    Options the per-mesh config does not set are still inherited from
    ``realistic_global_init.cfg``.
    """
    config = _get_init_config(mesh_name)
    section = config['vertical_grid']
    assert section.get('coord_type') == 'p-star'
    assert section.getint('min_vert_levels') == 3
    assert section.getfloat('min_bottom_depth') == 10.0


def test_mesh_without_config_keeps_defaults():
    """A mesh with no per-mesh config keeps the default vertical grid."""
    config = _get_init_config('icos120km')
    assert config.get('vertical_grid', 'grid_type') == '80layerE3SMv1'
