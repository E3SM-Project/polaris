from polaris.component import Component
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.e3sm.init.topo.cull.tasks import add_cull_topo_tasks
from polaris.tasks.e3sm.init.topo.remap.tasks import add_remap_topo_tasks


def test_add_remap_topo_tasks_includes_unified_meshes():
    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)

    for mesh_name in UNIFIED_MESH_NAMES:
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
    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)

    mesh_name = 'u.oi240.lr240'
    task = component.tasks[f'{mesh_name}/topo/remap']

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
    component = Component(name='e3sm/init')
    add_cull_topo_tasks(component=component)

    for mesh_name in UNIFIED_MESH_NAMES:
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
    component = Component(name='e3sm/init')
    add_cull_topo_tasks(component=component)

    mesh_name = 'u.oi240.lr240'
    task = component.tasks[f'{mesh_name}/topo/cull']

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
        'cull_mask',
        'cull_mesh',
    ]


def test_coarse_unified_mesh_uses_ne120_topography():
    component = Component(name='e3sm/init')
    add_remap_topo_tasks(component=component)
    add_cull_topo_tasks(component=component)

    mesh_name = 'u.oi240.lr240'
    remap_task = component.tasks[f'{mesh_name}/topo/remap']
    cull_task = component.tasks[f'{mesh_name}/topo/cull']

    assert remap_task.combine_topo_step.subdir.endswith('cubed_sphere/ne120')
    assert cull_task.combine_topo_step.subdir.endswith('cubed_sphere/ne120')
