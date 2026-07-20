import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.init.woa23_map import Woa23MapStep
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
)


class _FakeComponent:
    name = 'ocean'


class _FakeStep:
    path = 'fake/step'


def _get_init_config(mesh_name):
    """
    Build a config the way ``_get_init_config`` in ``init/steps.py`` does.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.remap', 'mapping.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'realistic_global_init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


def _make_step(mesh_name):
    step = Woa23MapStep(
        component=_FakeComponent(),
        subdir=f'{mesh_name}/woa23_map',
        extrapolate_step=_FakeStep(),
        cull_mesh_step=_FakeStep(),
        mesh_name=mesh_name,
    )
    step.config = _get_init_config(mesh_name)
    return step


def test_method_is_bilinear():
    """
    Bilinear is set explicitly rather than relying on the pyremap default.
    """
    step = _make_step('icos240km')
    assert step.remapper.method == 'bilinear'


def test_does_not_use_tmp():
    """
    /tmp is node-local on Chrysalis, so a multi-node mbtempest cannot read
    SCRIP files placed there.
    """
    step = _make_step('icos240km')
    assert step.remapper.use_tmp is False


def test_map_tool_comes_from_mapping_config():
    config = _get_init_config('icos240km')
    assert config.get('mapping', 'map_tool') == 'moab'


@pytest.mark.parametrize('mesh_name', ['icos240km', 'icos60km'])
def test_update_ntasks_from_cell_count(mesh_name):
    """
    ntasks and min_tasks follow the cell count and the per-task cell counts.
    """
    step = _make_step(mesh_name)
    step._update_ntasks()

    config = step.config
    cell_count = estimate_ocean_cell_count(mesh_name, config=config)
    section = config['realistic_global_init']
    expected_ntasks = max(
        1, round(cell_count / section.getint('remap_cells_per_task'))
    )
    expected_min = max(
        1, round(cell_count / section.getint('remap_min_cells_per_task'))
    )

    assert step.ntasks == expected_ntasks
    assert step.min_tasks == expected_min
    assert step.min_tasks <= step.ntasks


def test_update_ntasks_is_modest_for_a_coarse_mesh():
    """
    A coarse mesh should not ask for a large number of tasks.  This guards
    against the per-task cell counts being set too small again.
    """
    step = _make_step('icos240km')
    step._update_ntasks()
    assert step.ntasks < 64


def test_update_ntasks_without_cell_count_leaves_defaults():
    """
    If the cell count cannot be estimated, ntasks falls back to the value set
    in the constructor rather than raising.
    """
    step = _make_step('icos240km')
    # a config with no per-mesh cell count and no mesh info to fall back on
    step.mesh_name = 'not_a_real_mesh'
    step.ntasks = 1
    step.min_tasks = 1
    step._update_ntasks()
    assert step.ntasks == 1
    assert step.min_tasks == 1
