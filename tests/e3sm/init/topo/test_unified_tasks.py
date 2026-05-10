from polaris.component import Component
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.cull import (
    CullTopoTask,
    get_cull_topo_steps,
)
from polaris.tasks.e3sm.init.topo.cull.tasks import add_cull_topo_tasks
from polaris.tasks.e3sm.init.topo.remap import (
    RemapTopoTask,
    get_remap_topo_steps,
)
from polaris.tasks.e3sm.init.topo.remap.tasks import add_remap_topo_tasks
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.mesh.base.steps import get_base_mesh_steps

COARSE_MESH_NAME = 'u.oi240.lr240'
FINE_MESH_NAME = 'u.oi30.lr10'


def test_get_remap_topo_steps_includes_upstream_base_mesh_steps():
    _reset_shared_components()

    base_mesh_steps, _ = get_base_mesh_steps(
        mesh_name=COARSE_MESH_NAME, include_viz=False
    )
    steps, _ = get_remap_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=True,
    )

    assert list(steps)[: len(base_mesh_steps)] == list(base_mesh_steps)
    assert list(steps)[len(base_mesh_steps) :] == [
        'combine_topo_cubed_sphere_ne120',
        'mask_topo',
        'remap_unsmoothed_topo',
        'viz_remapped_unsmoothed_topo',
        'remap_smoothed_topo',
        'viz_remapped_smoothed_topo',
    ]


def test_get_cull_topo_steps_includes_full_remap_workflow():
    _reset_shared_components()

    remap_steps, _ = get_remap_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=False,
    )
    cull_steps, _ = get_cull_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        include_viz=False,
    )

    assert list(cull_steps) == list(remap_steps) + ['cull_mask', 'cull_mesh']


def test_get_remap_topo_steps_uses_mesh_max_cell_width_for_source_topography():
    _reset_shared_components()

    coarse_steps, _ = get_remap_topo_steps(mesh_name=COARSE_MESH_NAME)
    fine_steps, _ = get_remap_topo_steps(mesh_name=FINE_MESH_NAME)

    assert coarse_steps['combine_topo_cubed_sphere_ne120'].subdir.endswith(
        'cubed_sphere/ne120'
    )
    assert fine_steps['combine_topo_cubed_sphere_ne3000'].subdir.endswith(
        'cubed_sphere/ne3000'
    )


def test_get_remap_topo_steps_reuses_shared_config_for_viz():
    _reset_shared_components()

    steps_without_viz, config_without_viz = get_remap_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=False,
    )
    steps_with_viz, config_with_viz = get_remap_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=True,
    )

    non_viz = {
        key: step
        for key, step in steps_with_viz.items()
        if not key.startswith('viz_')
    }

    assert non_viz == steps_without_viz
    assert config_without_viz is config_with_viz
    assert config_with_viz is e3sm_init.configs[config_with_viz.filepath]


def test_remap_topo_task_uses_factory_symlink_keys():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    steps, _ = get_remap_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=True,
    )
    task = RemapTopoTask(
        component=component,
        mesh_name=COARSE_MESH_NAME,
        smoothing=True,
        include_viz=True,
    )

    assert list(task.steps) == [step.name for step in steps.values()]
    assert task.step_symlinks == {
        step.name: symlink for symlink, step in steps.items()
    }


def test_cull_topo_task_uses_factory_symlink_keys():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    steps, _ = get_cull_topo_steps(
        mesh_name=COARSE_MESH_NAME,
        include_viz=True,
    )
    task = CullTopoTask(
        component=component,
        mesh_name=COARSE_MESH_NAME,
        include_viz=True,
    )

    assert list(task.steps) == [step.name for step in steps.values()]
    assert task.step_symlinks == {
        step.name: symlink for symlink, step in steps.items()
    }


def test_add_remap_topo_tasks_includes_unified_meshes():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)

    for mesh_name in [COARSE_MESH_NAME, FINE_MESH_NAME]:
        subdir = f'{mesh_name}/topo/remap'
        assert subdir in component.tasks
        task = component.tasks[subdir]
        assert task.name == f'{mesh_name}_topo_remap_task'
        assert task.config.has_option(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        assert (
            task.config.get('spherical_mesh', 'antarctic_boundary_convention')
            == 'calving_front'
        )


def test_unified_remap_topo_task_includes_base_mesh_dependencies():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)

    task = component.tasks[f'{COARSE_MESH_NAME}/topo/remap']

    assert list(task.steps.keys()) == [
        'combine_topo_bedmap3_gebco2023_lat_lon_0.03125_degree',
        'coastline_compute',
        'coastline_remap',
        'river_simplify',
        'river_rasterize',
        'river_clip',
        'sizing_field',
        'base_mesh',
        'combine_topo_bedmap3_gebco2023_cubed_sphere_ne120',
        'mask_topo',
        'remap_unsmoothed',
        'viz_remapped_unsmoothed',
        'remap_smoothed',
        'viz_remapped_smoothed',
    ]


def test_add_cull_topo_tasks_includes_unified_meshes():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_cull_topo_tasks(component=component)

    for mesh_name in [COARSE_MESH_NAME, FINE_MESH_NAME]:
        subdir = f'{mesh_name}/topo/cull'
        assert subdir in component.tasks
        task = component.tasks[subdir]
        assert task.name == f'{mesh_name}_cull_topo_task'
        assert task.config.has_option(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        assert (
            task.config.get('spherical_mesh', 'antarctic_boundary_convention')
            == 'calving_front'
        )


def test_unified_cull_topo_task_includes_base_mesh_dependencies():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_cull_topo_tasks(component=component)

    task = component.tasks[f'{COARSE_MESH_NAME}/topo/cull']

    assert list(task.steps.keys()) == [
        'combine_topo_bedmap3_gebco2023_lat_lon_0.03125_degree',
        'coastline_compute',
        'coastline_remap',
        'river_simplify',
        'river_rasterize',
        'river_clip',
        'sizing_field',
        'base_mesh',
        'combine_topo_bedmap3_gebco2023_cubed_sphere_ne120',
        'mask_topo',
        'remap_unsmoothed',
        'remap_smoothed',
        'cull_mask',
        'cull_mesh',
    ]


def test_coarse_unified_mesh_uses_ne120_topography():
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)
    add_cull_topo_tasks(component=component)

    remap_task = component.tasks[f'{COARSE_MESH_NAME}/topo/remap']
    cull_task = component.tasks[f'{COARSE_MESH_NAME}/topo/cull']

    combine_topo_step_name = (
        'combine_topo_bedmap3_gebco2023_cubed_sphere_ne120'
    )
    assert remap_task.steps[combine_topo_step_name].subdir.endswith(
        'cubed_sphere/ne120'
    )
    assert cull_task.steps[combine_topo_step_name].subdir.endswith(
        'cubed_sphere/ne120'
    )


def _reset_shared_components():
    for component in [e3sm_init, mesh_component]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
