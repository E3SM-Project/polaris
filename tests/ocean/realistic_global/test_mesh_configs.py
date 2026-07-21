import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
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


# -----------------------------------------------------------------------
# forward-run overrides
# -----------------------------------------------------------------------


def _get_forward_stage(mesh_name):
    """Build the ForwardStage a forward step would use for one mesh."""
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'realistic_global_forward.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    config.combine()
    return ForwardStage.from_config(config)


# expected per-mesh forward settings, ported from the Compass mesh named in
# the comment.  These are what keep a forward run stable, so they are checked
# explicitly rather than through a round trip.
FORWARD_EXPECTED: dict[str, dict[str, object]] = {
    # Compass qu240
    'u.oi240.lr240': dict(
        mom_del2=1.0e3,
        mom_del4=1.2e11,
        tracer_del2=10.0,
        tracer_del4=1.2e11,
        use_Leith_del2=True,
        hmix_scaling='ref_cell_width',
        use_GM=True,
        use_Redi=True,
        use_frazil_ice_formation=True,
    ),
    # Compass qu
    'u.oi30.lr10': dict(
        mom_del2=1.0e3,
        mom_del4=1.2e11,
        tracer_del2=None,
        use_Leith_del2=False,
        hmix_scaling='ref_cell_width',
        use_GM=True,
        use_Redi=True,
        use_frazil_ice_formation=False,
    ),
    # Compass rrs6to18
    'u.oi6to18.lr6to10': dict(
        mom_del2=None,
        mom_del4=3.2e09,
        hmix_scaling='scale_with_mesh',
        use_GM=False,
        use_Redi=False,
        dt_per_km=10.0,
        btr_dt_per_km=0.5,
    ),
    # Compass so12to30, apart from its time step
    'u.oi.so12to30.lr10': dict(
        mom_del2=462.0,
        mom_del4=1.18e10,
        hmix_scaling='scale_with_mesh',
        use_GM=True,
        GM_closure='constant',
        GM_constant_kappa=600.0,
        dt_per_km=30.0,
        btr_dt_per_km=1.5,
    ),
}


@pytest.mark.parametrize('mesh_name', sorted(FORWARD_EXPECTED))
def test_forward_overrides(mesh_name):
    stage = _get_forward_stage(mesh_name)
    for option, expected in FORWARD_EXPECTED[mesh_name].items():
        assert getattr(stage, option) == expected, option


@pytest.mark.parametrize('mesh_name', COARSE_MESH_NAMES)
def test_coarse_meshes_share_forward_settings(mesh_name):
    """
    The three 240 km meshes are qualitatively the same mesh and are configured
    by hand in three separate files, so they must not drift apart.
    """
    stage = _get_forward_stage(mesh_name)
    assert stage == _get_forward_stage('u.oi240.lr240')


def test_mesh_without_config_keeps_forward_defaults():
    stage = _get_forward_stage('icos120km')
    assert stage.hmix_scaling == 'none'
    assert stage.mom_del2 == 1.0e3
    assert not stage.use_Leith_del2
