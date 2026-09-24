from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
    get_woa23_topography_step,
)


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


def test_woa23_steps_hand_back_the_config_their_steps_use():
    component = Ocean()
    combine_topo_step = get_woa23_topography_step()

    first_steps, first_config = get_woa23_steps(
        component=component, combine_topo_step=combine_topo_step
    )
    second_steps, second_config = get_woa23_steps(
        component=component, combine_topo_step=combine_topo_step
    )

    assert second_config is first_config
    for name, step in first_steps.items():
        assert second_steps[name] is step, name
        assert step.config is first_config, name
    # and re-registering what was handed back is a no-op rather than an error
    component.add_config(second_config)
