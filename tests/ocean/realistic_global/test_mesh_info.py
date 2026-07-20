import pytest

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


def test_estimate_ocean_cell_count_unknown_mesh():
    assert estimate_ocean_cell_count('nonexistent_mesh_xyz') is None
