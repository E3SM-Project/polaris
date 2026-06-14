from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks


def test_add_realistic_global_tasks_registers_woa23():
    component = Ocean()

    add_realistic_global_tasks(component=component)

    task_subdir = 'spherical/realistic_global/hydrography/woa23'
    assert task_subdir in component.tasks
    old_task_subdir = f'{"global"}_ocean/hydrography/woa23'
    assert old_task_subdir not in component.tasks

    task = component.tasks[task_subdir]
    assert task.name == 'woa23'
    combine_topo_step_name = (
        'combine_topo_bedmap3_gebco2023_lat_lon_0.25000_degree'
    )
    assert list(task.steps) == [
        combine_topo_step_name,
        'combine',
        'extrapolate',
        'viz',
    ]
    assert task.step_symlinks[combine_topo_step_name] == 'combine_topo'
    assert 'spherical/realistic_global/hydrography/woa23/combine' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/extrapolate' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/viz' in (
        component.steps
    )


def test_add_realistic_global_tasks_registers_init_for_all_meshes():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    expected_mesh_names = list(get_base_mesh_step_names()) + list(
        UNIFIED_MESH_NAMES
    )
    for mesh_name in expected_mesh_names:
        task_subdir = f'spherical/realistic_global/init/{mesh_name}/task'
        assert task_subdir in component.tasks, (
            f'Expected init task for mesh={mesh_name!r} not found'
        )


def test_realistic_global_init_icos240km_steps():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    task_subdir = 'spherical/realistic_global/init/icos240km/task'
    assert task_subdir in component.tasks

    task = component.tasks[task_subdir]

    assert 'remap_woa23' in task.steps
    assert 'pstar_init' in task.steps
    assert 'initial_state' in task.steps
    assert 'cull_mesh' in task.steps
    assert 'extrapolate' in task.steps

    assert task.steps['remap_woa23'].subdir == (
        'spherical/realistic_global/init/icos240km/remap_woa23'
    )
    assert task.steps['pstar_init'].subdir == (
        'spherical/realistic_global/init/icos240km/pstar_init'
    )
    assert task.steps['initial_state'].subdir == (
        'spherical/realistic_global/init/icos240km/initial_state'
    )


def test_realistic_global_init_one_task_per_mesh():
    """Exactly one task is registered per mesh (no model variants)."""
    component = Ocean()
    add_realistic_global_tasks(component=component)

    expected_mesh_names = list(get_base_mesh_step_names()) + list(
        UNIFIED_MESH_NAMES
    )
    for mesh_name in expected_mesh_names:
        task_subdir = f'spherical/realistic_global/init/{mesh_name}/task'
        assert task_subdir in component.tasks
        # Confirm there is no model-qualified variant
        for model in ('omega', 'mpas-ocean'):
            model_subdir = (
                f'spherical/realistic_global/init/{mesh_name}/{model}'
            )
            assert model_subdir not in component.tasks, (
                f'Unexpected per-model task found: {model_subdir!r}'
            )
