from polaris.component import Component
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.mesh.spherical.unified.base_mesh import (
    add_unified_base_mesh_tasks,
    get_unified_base_mesh_steps,
)


def test_add_unified_base_mesh_tasks_registers_named_meshes():
    component = Component(name='mesh')
    add_unified_base_mesh_tasks(component=component)

    assert len(component.tasks) == len(UNIFIED_MESH_NAMES)
    for mesh_name in UNIFIED_MESH_NAMES:
        subdir = f'spherical/unified/{mesh_name}/base_mesh/task'
        assert subdir in component.tasks
        task = component.tasks[subdir]
        assert task.name == f'base_mesh_{mesh_name}_task'


def test_add_unified_base_mesh_task_includes_dependencies():
    component = Component(name='mesh')
    add_unified_base_mesh_tasks(component=component)

    mesh_name = 'u.oi240.lr240'
    subdir = f'spherical/unified/{mesh_name}/base_mesh/task'
    task = component.tasks[subdir]

    # note that the step names disagree somewhat with the suggested symlinks
    # returned by get_unified_base_mesh_steps() in
    # test_base_mesh_step_factory_includes_dependencies() below.
    assert list(task.steps.keys()) == [
        'combine_topo_bedmap3_gebco2023_lat_lon_0.03125_degree',
        'coastline_compute',
        'coastline_remap',
        'river_simplify',
        'river_rasterize',
        'river_clip',
        'sizing_field',
        'base_mesh',
        'base_mesh_viz',
    ]


def test_base_mesh_step_factory_uses_mesh_subdir_and_viz():
    mesh_name = 'u.oi30.lr10'

    steps, config = get_unified_base_mesh_steps(
        mesh_name=mesh_name,
        include_viz=True,
    )

    assert steps['base_mesh'].subdir == (
        f'spherical/unified/{mesh_name}/base_mesh/build'
    )
    assert steps['base_mesh_viz'].subdir == (
        f'spherical/unified/{mesh_name}/base_mesh/viz'
    )
    assert config.get('unified_mesh', 'mesh_name') == mesh_name
    assert config.has_section('spherical_mesh')
    assert config.has_option('spherical_mesh', 'antarctic_boundary_convention')
    assert config.has_section('viz_unified_base_mesh')


def test_base_mesh_step_factory_includes_dependencies():
    mesh_name = 'u.oi30.lr10'

    steps, _ = get_unified_base_mesh_steps(
        mesh_name=mesh_name,
    )

    assert list(steps) == [
        'combine_topo_lat_lon_0.03125_degree',
        'coastline_compute',
        'coastline_final',
        'river_simplify',
        'river_rasterize',
        'river_clip',
        'sizing_field',
        'base_mesh',
    ]


def test_base_mesh_step_factory_reuses_shared_config_for_viz():
    mesh_name = 'u.oi30.lr10'

    build_steps, _ = get_unified_base_mesh_steps(
        mesh_name=mesh_name,
        include_viz=False,
    )
    steps, config = get_unified_base_mesh_steps(
        mesh_name=mesh_name,
        include_viz=True,
    )
    component = steps['base_mesh'].component

    non_viz = {k: v for k, v in steps.items() if k != 'base_mesh_viz'}
    assert non_viz == build_steps
    # 1 combine topo, 2 coastline, 3 river, 1 sizing field, 1 base mesh, and
    # optionally 1 viz
    assert len(steps) == 9
    assert config is component.configs[config.filepath]
