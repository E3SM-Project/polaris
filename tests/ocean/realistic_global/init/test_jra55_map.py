import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.init.jra55_map import Jra55MapStep
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
    config = PolarisConfigParser()
    config.add_from_package('polaris.remap', 'mapping.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'realistic_global_init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


def _make_step(mesh_name):
    step = Jra55MapStep(
        component=_FakeComponent(),
        subdir=f'{mesh_name}/jra55_map',
        stress_step=_FakeStep(),
        cull_mesh_step=_FakeStep(),
        mesh_name=mesh_name,
    )
    step.config = _get_init_config(mesh_name)
    return step


def test_method_is_bilinear():
    """
    Bilinear, not conservative.  The ocean responds to wind stress curl, and
    first-order conservative remapping makes that curl grid-scale noise;
    pyremap's moab path hard-codes --order 1, so second-order conservative is
    not available.  See remap_bilinear_pole_findings.md before changing this.
    """
    step = _make_step('icos240km')
    assert step.remapper.method == 'bilinear'


def test_map_tool_is_left_at_the_polaris_default():
    """
    ESMF must not be selected here.  Its default pole handling builds the
    pole point from the zonal average of the source's outermost row, which
    collapses a vector field to zero at the pole.
    """
    step = _make_step('icos240km')
    assert step.config.get('mapping', 'map_tool') == 'moab'


@pytest.mark.parametrize('mesh_name', ['icos240km', 'qu60km'])
def test_update_ntasks_from_cell_count(mesh_name):
    step = _make_step(mesh_name)
    step._update_ntasks()

    config = step.config
    cell_count = estimate_ocean_cell_count(mesh_name, config=config)
    assert cell_count is not None
    section = config['realistic_global_init']
    cells_per_task = section.getint('remap_cells_per_task')
    min_cells_per_task = section.getint('remap_min_cells_per_task')

    assert step.ntasks == max(1, round(cell_count / cells_per_task))
    assert step.min_tasks == max(1, round(cell_count / min_cells_per_task))


def test_update_ntasks_never_asks_for_no_tasks():
    """
    Rounding a small cell count can reach zero, which is not a task count a
    step can run with.
    """
    step = _make_step('icos240km')
    step._update_ntasks()
    assert step.ntasks >= 1
    assert step.min_tasks >= 1
