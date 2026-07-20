import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_cell_count,
    estimate_ocean_cell_count,
)

# -----------------------------------------------------------------------
# estimate_cell_count
# -----------------------------------------------------------------------


def test_estimate_cell_count_icos_base_mesh():
    count = estimate_cell_count('icos240km')
    # formula: 6e8 / 240**2 ≈ 10417
    assert count is not None
    assert count == pytest.approx(6e8 / 240**2, rel=1e-6)


def test_estimate_cell_count_qu_base_mesh():
    count = estimate_cell_count('qu30km')
    # formula: 6e8 / 30**2 ≈ 666667
    assert count is not None
    assert count == pytest.approx(6e8 / 30**2, rel=1e-6)


def test_estimate_cell_count_unified_mesh_returns_int_or_none():
    """Unified meshes with approximate_cell_count set return a positive int."""
    count = estimate_cell_count('u.oi240.lr240')
    assert count is not None
    assert count > 0


def test_estimate_cell_count_unknown_mesh():
    count = estimate_cell_count('nonexistent_mesh_xyz')
    assert count is None


# -----------------------------------------------------------------------
# estimate_ocean_cell_count
# -----------------------------------------------------------------------


def test_estimate_ocean_cell_count_uses_culled_option():
    """The ocean-culled count is read from culled_ocean_cell_count."""
    count = estimate_ocean_cell_count('u.oi30.lr10')
    assert count == 470000
    # it should be much smaller than the full-mesh estimate
    assert count < estimate_cell_count('u.oi30.lr10')


def test_estimate_ocean_cell_count_falls_back_to_full():
    """Base meshes have no culled option, so fall back to the full estimate."""
    assert estimate_ocean_cell_count('icos240km') == estimate_cell_count(
        'icos240km'
    )


@pytest.mark.parametrize('mesh_name', UNIFIED_MESH_NAMES)
def test_unified_meshes_define_ocean_cell_count(mesh_name):
    """
    Every unified mesh sets culled_ocean_cell_count, and it is smaller than
    the full-mesh count, which includes land and river refinement.
    """
    count = estimate_ocean_cell_count(mesh_name)
    assert count is not None
    assert 0 < count < estimate_cell_count(mesh_name)


def test_estimate_ocean_cell_count_unknown_mesh():
    assert estimate_ocean_cell_count('nonexistent_mesh_xyz') is None


def test_estimate_ocean_cell_count_uses_given_config():
    """A config passed by the caller is used instead of the package file."""
    config = PolarisConfigParser()
    add_realistic_global_mesh_config(config, 'u.oi30.lr10')
    config.set('realistic_global_mesh', 'culled_ocean_cell_count', '12345')
    assert estimate_ocean_cell_count('u.oi30.lr10', config=config) == 12345
    # without the config, the value from the package file is used
    assert estimate_ocean_cell_count('u.oi30.lr10') == 470000


def test_estimate_ocean_cell_count_given_config_without_option():
    """
    A config with no culled count still falls back to the full-mesh estimate.
    """
    config = PolarisConfigParser()
    add_realistic_global_mesh_config(config, 'icos240km')
    assert estimate_ocean_cell_count(
        'icos240km', config=config
    ) == estimate_cell_count('icos240km')
