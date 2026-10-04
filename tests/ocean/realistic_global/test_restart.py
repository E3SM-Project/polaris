import pytest

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
)
from polaris.tasks.ocean.realistic_global.restart import (
    FULL_DURATION,
    SEGMENT_DURATION,
)
from polaris.yaml import PolarisYaml

TASK_SUBDIR = 'spherical/realistic_global/QU.240km/restart'


def _restart_task(model='omega'):
    """The registered restart task, with its config combined for ``model``"""
    component = Ocean()
    add_realistic_global_tasks(component=component)
    task = component.tasks[TASK_SUBDIR]
    config = task.config
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.set('ocean', 'model', model)
    config.combine()
    return task


def _model_config_entry(step, package, yaml):
    """The replacements a step's dynamic model config gave ``yaml``"""
    for entry in step.model_config_data:
        if entry.get('package') == package and entry.get('yaml') == yaml:
            return entry['replacements']
    raise AssertionError(f'{package}/{yaml} was not added to {step.name}')


def test_restart_task_is_registered_on_the_cached_qu240():
    task = _restart_task()
    assert list(task.steps) == [
        'full_run',
        'first_segment',
        'second_segment',
        'validate',
    ]
    for name in ['full_run', 'first_segment', 'second_segment']:
        step = task.steps[name]
        assert isinstance(step.init_condition, DatabaseInitialCondition)
        assert step.init_condition.mesh_name == 'QU.240km'

    # the continuing segment depends on the first through its history file
    inputs = [
        entry['filename'] for entry in task.steps['second_segment'].input_data
    ]
    assert 'previous_output.nc' in inputs


@pytest.mark.parametrize(
    'name, run_duration, start_type, read_dir',
    [
        ('full_run', FULL_DURATION, 'StartUp', '../restarts/full_run'),
        (
            'first_segment',
            SEGMENT_DURATION,
            'StartUp',
            '../restarts/first_segment',
        ),
        (
            'second_segment',
            SEGMENT_DURATION,
            'Continue',
            '../restarts/first_segment',
        ),
    ],
)
def test_restart_steps_run_the_same_model_for_their_own_duration(
    name, run_duration, start_type, read_dir
):
    """
    Every step runs the same forward configuration -- split-explicit Omega on
    the restart task's time steps and viscosity -- and differs only in its
    duration and where its restart comes from.
    """
    step = _restart_task().steps[name]
    step.dynamic_model_config(at_setup=True)

    replacements = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.forward', 'forward.yaml'
    )
    assert replacements['time_integrator'] == 'SplitExplicitRK2'
    assert replacements['dt'] == '01:00:00'
    assert replacements['btr_dt'] == '00:03:00'
    assert replacements['run_duration'] == run_duration
    assert replacements['output_freq'] == '3600'

    mixing = [
        entry['options']
        for entry in step.model_config_data
        if 'options' in entry and 'config_mom_del4' in entry['options']
    ]
    assert mixing == [
        {
            'config_use_mom_del2': True,
            'config_mom_del2': 1.0e3,
            'config_use_mom_del4': True,
            'config_mom_del4': 1.0e15,
            'config_use_tracer_del2': False,
            'config_use_tracer_del4': False,
        }
    ]

    overlay = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.restart', 'forward.yaml'
    )
    assert overlay['start_type'] == start_type
    assert overlay['restart_read_dir'] == read_dir
    assert overlay['restart_write_dir'] == f'../restarts/{name}'

    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.realistic_global.restart',
        replacements=overlay,
        model='Omega',
        streams_section='IOStreams',
    )
    time_integration = yaml.configs['TimeIntegration']
    assert time_integration['StartType'] == start_type
    # the simulation start, not the segment's, which is what Omega #482 was
    # about
    assert time_integration['StartTime'] == '0001-01-01_00:00:00'
    streams = yaml.streams
    assert (
        streams['RestartRead']['PointerFilename'] == f'{read_dir}/ocn.pointer'
    )


def test_restart_task_rejects_mpas_ocean():
    step = _restart_task(model='mpas-ocean').steps['first_segment']
    with pytest.raises(ValueError, match='supports only Omega'):
        step.setup()
