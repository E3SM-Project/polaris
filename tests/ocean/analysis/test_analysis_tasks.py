import pytest

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import add_analysis_tasks
from polaris.tasks.ocean.analysis.climatology_maps import get_field_groups

TASK_SUBDIRS = [
    'analysis/climatology_maps',
    'analysis/global_stats',
    'analysis/heat_content_series',
    'analysis/moc',
]

FIELD_GROUPS = [
    'temperature',
    'salinity',
    'velocity',
    'ssh',
    'mixed_layer_depth',
    'heat_content',
]


def _make_component():
    """A fresh ocean component with only the analysis tasks in it."""
    component = Ocean()
    add_analysis_tasks(component)
    return component


def _step_subdirs(component, task_subdir):
    return [
        step.subdir for step in component.tasks[task_subdir].steps.values()
    ]


def _set_range(component, section, start_year, end_year):
    """Set a year range the way a user's config file would, and reconfigure."""
    config = component.tasks['analysis/moc'].config
    config.set(section, 'start_year', str(start_year), user=True)
    config.set(section, 'end_year', str(end_year), user=True)
    for task_subdir in TASK_SUBDIRS:
        component.tasks[task_subdir].configure()


def test_the_suite_has_one_task_per_product():
    component = _make_component()
    assert sorted(component.tasks) == sorted(TASK_SUBDIRS)


def test_steps_land_at_range_keyed_subdirectories():
    """The work tree is <product>/<range>, with a field group below the one
    product that is chunked."""
    component = _make_component()
    _set_range(component, 'ocean_analysis_climatology', 21, 40)
    _set_range(component, 'ocean_analysis_time_series', 1, 60)

    assert _step_subdirs(component, 'analysis/climatology_maps') == [
        'analysis/climatology/0021-0040',
    ] + [
        f'analysis/climatology_maps/0021-0040/{group}'
        for group in FIELD_GROUPS
    ]
    assert _step_subdirs(component, 'analysis/global_stats') == [
        'analysis/global_stats/0001-0060'
    ]
    assert _step_subdirs(component, 'analysis/heat_content_series') == [
        'analysis/heat_content_series/0001-0060'
    ]
    assert _step_subdirs(component, 'analysis/moc') == [
        'analysis/moc/0021-0040'
    ]


def test_changing_the_range_moves_the_steps():
    """A new range is new directories, which have never run and so run."""
    component = _make_component()
    before = _step_subdirs(component, 'analysis/moc')
    _set_range(component, 'ocean_analysis_climatology', 21, 40)
    after = _step_subdirs(component, 'analysis/moc')
    assert before == ['analysis/moc/0001-0010']
    assert after == ['analysis/moc/0021-0040']
    assert 'analysis/moc/0001-0010' not in component.steps


def test_the_two_ranges_are_independent():
    """Changing the climatology does not disturb the time series, or the
    other way around."""
    component = _make_component()
    _set_range(component, 'ocean_analysis_climatology', 21, 40)
    assert _step_subdirs(component, 'analysis/global_stats') == [
        'analysis/global_stats/0001-0010'
    ]

    _set_range(component, 'ocean_analysis_time_series', 1, 60)
    assert _step_subdirs(component, 'analysis/moc') == [
        'analysis/moc/0021-0040'
    ]


def test_the_climatology_is_shared_by_every_field_group():
    """One ncclimo call for a range, no matter how many maps read it."""
    component = _make_component()
    task = component.tasks['analysis/climatology_maps']
    climatology = task.steps['climatology']
    assert climatology.subdir == 'analysis/climatology/0001-0010'
    assert component.steps['analysis/climatology/0001-0010'] is climatology
    assert task.step_symlinks['climatology'] == 'climatology'


def test_the_climatology_declares_ncclimo_s_processes():
    """The pool is sized from what the step will start, not from the
    machine."""
    component = _make_component()
    climatology = component.tasks['analysis/climatology_maps'].steps[
        'climatology'
    ]
    assert climatology.ntasks == 1
    assert climatology.cpus_per_task == 12


def test_the_default_fields_cover_every_field_group():
    component = _make_component()
    config = component.tasks['analysis/climatology_maps'].config
    fields = config.getlist('ocean_analysis_climatology', 'fields')
    assert list(get_field_groups(fields)) == FIELD_GROUPS


def test_fewer_fields_means_fewer_steps():
    """The field list is an axis a user edits, so adding a field should cost
    that field and not the others."""
    component = _make_component()
    config = component.tasks['analysis/climatology_maps'].config
    config.set(
        'ocean_analysis_climatology',
        'fields',
        'temperature, velocityZonal',
        user=True,
    )
    component.tasks['analysis/climatology_maps'].configure()
    assert _step_subdirs(component, 'analysis/climatology_maps') == [
        'analysis/climatology/0001-0010',
        'analysis/climatology_maps/0001-0010/temperature',
        'analysis/climatology_maps/0001-0010/velocity',
        'analysis/climatology_maps/0001-0010/heat_content',
    ]


def test_a_field_in_no_group_is_named_in_the_error():
    with pytest.raises(ValueError, match='belongs to no field group'):
        get_field_groups(['temperature', 'notAField'])


def test_heat_content_is_a_group_even_though_it_is_derived():
    """Heat content is a field group of the maps rather than a product of its
    own, and it is not a field a user lists."""
    groups = get_field_groups(['temperature'])
    assert list(groups) == ['temperature', 'heat_content']
    assert groups['heat_content'] == []
