import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
from polaris.tasks.ocean.realistic_global.forward.tasks import CACHED_MESHES
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
    get_mesh_config_names,
    get_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.mesh_info import min_res_for_mesh

# meshes that override the default vertical grid with a cheap, coarse one
COARSE_MESH_NAMES = ('qu240km', 'icos240km', 'u-oi240-lr240')


def _get_init_config(mesh_name):
    """
    Build a config the way ``_get_init_config`` in ``init/steps.py`` does.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'init.cfg',
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
    # the cached meshes are real meshes too; Polaris does not build them, but
    # it runs forward tasks on them from cached initial conditions
    valid_mesh_names = (
        set(get_base_mesh_step_names())
        | set(UNIFIED_MESH_NAMES)
        | set(CACHED_MESHES)
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
def test_mesh_config_overrides_init_cfg(mesh_name):
    """
    The per-mesh config wins over ``init.cfg`` for the options it sets, and
    options it does not set are still inherited from ``init.cfg``.
    """
    config = _get_init_config(mesh_name)
    mesh_config = get_realistic_global_mesh_config(mesh_name)
    defaults = _get_init_config('icos120km')
    section = 'vertical_grid'
    assert mesh_config.has_section(section)
    for option in mesh_config.options(section):
        assert config.get(section, option) == mesh_config.get(
            section, option
        ), option
    for option in defaults.options(section):
        if not mesh_config.has_option(section, option):
            assert config.get(section, option) == defaults.get(
                section, option
            ), option


# -----------------------------------------------------------------------
# forward-run overrides
# -----------------------------------------------------------------------


def _get_forward_stage(mesh_name):
    """Build the ForwardStage a forward step would use for one mesh."""
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'forward.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    config.combine()
    return ForwardStage.from_config(config)


@pytest.mark.parametrize(
    'mesh_name',
    [
        mesh_name
        for mesh_name in get_mesh_config_names()
        if mesh_name not in CACHED_MESHES
        and _get_forward_stage(mesh_name).hmix_ref_cell_width is not None
    ],
)
def test_stated_references_are_the_finest_cells(mesh_name):
    """
    A mesh states hmix_ref_cell_width only when its coefficients come from
    E3SM or Compass, whose per-grid values are referenced to the finest cells
    of the mesh they belong to, so the reference has to be that resolution.
    Getting this wrong is silent: every cell but the reference then runs at
    the wrong viscosity, and on a 240 km mesh a 30 km reference makes the
    biharmonic viscosity about 500 times larger.  The cached meshes are
    checked in test_tasks.py instead, since their minimum resolution is a
    measured dcEdge rather than the resolution the mesh was designed for.
    """
    stage = _get_forward_stage(mesh_name)
    assert stage.hmix_ref_cell_width == min_res_for_mesh(mesh_name) * 1.0e3


@pytest.mark.parametrize('mesh_name', COARSE_MESH_NAMES)
def test_coarse_meshes_share_forward_settings(mesh_name):
    """
    The three 240 km meshes are qualitatively the same mesh and are configured
    by hand in three separate files, so they must not drift apart.
    """
    stage = _get_forward_stage(mesh_name)
    assert stage == _get_forward_stage('u-oi240-lr240')
