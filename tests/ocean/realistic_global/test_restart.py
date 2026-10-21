import pytest

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
)
from polaris.tasks.ocean.realistic_global.restart import (
    FULL_DURATION,
    RESTART_DURATION,
)
from polaris.tasks.ocean.realistic_global.restart.restart_step import (
    BEFORE_RESTART_FILENAME,
)
from polaris.yaml import PolarisYaml

TASK_SUBDIR = 'spherical/realistic_global/e3sm-qu240/restart'

FORWARD_PACKAGE = 'polaris.tasks.ocean.realistic_global.forward'
RESTART_PACKAGE = 'polaris.tasks.ocean.realistic_global.restart'

#: The full run's restart at the restart time, two hours in, relative to the
#: steps' work directories
RESTART_FILE = '../restarts/full_run/ocn.restart.0001-01-01_02.00.00.nc'


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


def _read_omega_yaml(package, yaml, replacements):
    """An Omega yaml file of ``package``, with its replacements filled in"""
    return PolarisYaml.read(
        filename=yaml,
        package=package,
        replacements=replacements,
        model='Omega',
        streams_section='IOStreams',
    )


def test_restart_task_is_registered_on_the_cached_qu240():
    task = _restart_task()
    assert list(task.steps) == ['full_run', 'restart_run', 'validate']
    for name in ['full_run', 'restart_run']:
        step = task.steps[name]
        assert isinstance(step.init_condition, DatabaseInitialCondition)
        # the database still names the files by E3SM's QU.240km
        assert step.init_condition.mesh_name == 'QU.240km'

    # the restart run appends to the full run's history up to the restart
    inputs = [
        entry['filename'] for entry in task.steps['restart_run'].input_data
    ]
    assert 'previous_output.nc' in inputs

    # and validate checks that history, as well as the two final ones
    inputs = [entry['filename'] for entry in task.steps['validate'].input_data]
    assert inputs == [
        'output_full_run.nc',
        'output_restart_run.nc',
        'output_before_restart.nc',
    ]


@pytest.mark.parametrize(
    'name, run_duration, overlay_yaml, start_type',
    [
        ('full_run', FULL_DURATION, 'full_run.yaml', 'StartUp'),
        ('restart_run', RESTART_DURATION, 'restart_run.yaml', 'Continue'),
    ],
)
def test_restart_steps_run_the_same_model_for_their_own_duration(
    name, run_duration, overlay_yaml, start_type
):
    """
    Both runs use the same forward configuration -- split-explicit Omega on
    e3sm-qu240's time steps and viscosity -- and differ only in their duration
    and their restarts.
    """
    step = _restart_task().steps[name]
    step.dynamic_model_config(at_setup=True)

    replacements = _model_config_entry(step, FORWARD_PACKAGE, 'forward.yaml')
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

    overlay = _model_config_entry(step, RESTART_PACKAGE, overlay_yaml)
    assert overlay['restart_dir'] == f'../restarts/{name}'
    yaml = _read_omega_yaml(RESTART_PACKAGE, overlay_yaml, overlay)
    time_integration = yaml.configs['TimeIntegration']
    assert time_integration['StartType'] == start_type
    # the simulation start, even for the restart run, which is what Omega
    # #482 was about
    assert time_integration['StartTime'] == '0001-01-01_00:00:00'


def test_full_run_writes_the_restart_and_its_history_up_to_it():
    step = _restart_task().steps['full_run']
    step.dynamic_model_config(at_setup=True)
    overlay = _model_config_entry(step, RESTART_PACKAGE, 'full_run.yaml')
    streams = _read_omega_yaml(
        RESTART_PACKAGE, 'full_run.yaml', overlay
    ).streams

    restart_write = streams['RestartWrite']
    assert restart_write['UsePointerFile'] is False
    assert restart_write['Freq'] == 7200
    assert restart_write['FreqUnits'] == 'seconds'

    before_restart = streams['HistoryBeforeRestart']
    assert before_restart['Filename'] == BEFORE_RESTART_FILENAME
    assert before_restart['UseStartEnd'] is True
    assert before_restart['StartTime'] == '0001-01-01_00:00:00'
    # after the frame at the restart time, before the next one
    assert before_restart['EndTime'] == '0001-01-01_02:30:00'


def test_history_before_restart_matches_history():
    """
    The restart run appends to the history the full run wrote up to the
    restart, so that history has to be written the way the base History
    stream is, apart from where and when.
    """
    step = _restart_task().steps['full_run']
    step.dynamic_model_config(at_setup=True)
    base = _read_omega_yaml(
        FORWARD_PACKAGE,
        'forward.yaml',
        _model_config_entry(step, FORWARD_PACKAGE, 'forward.yaml'),
    ).streams['History']
    before_restart = _read_omega_yaml(
        RESTART_PACKAGE,
        'full_run.yaml',
        _model_config_entry(step, RESTART_PACKAGE, 'full_run.yaml'),
    ).streams['HistoryBeforeRestart']

    differ = ['Filename', 'UseStartEnd', 'StartTime', 'EndTime']
    for key in differ:
        base.pop(key, None)
        before_restart.pop(key, None)
    assert before_restart == base


def test_restart_run_reads_the_full_runs_restart_by_name():
    step = _restart_task().steps['restart_run']
    step.dynamic_model_config(at_setup=True)
    overlay = _model_config_entry(step, RESTART_PACKAGE, 'restart_run.yaml')
    assert overlay['restart_read_file'] == RESTART_FILE
    streams = _read_omega_yaml(
        RESTART_PACKAGE, 'restart_run.yaml', overlay
    ).streams
    assert streams['RestartRead']['UsePointerFile'] is False
    assert streams['RestartRead']['Filename'] == RESTART_FILE


def test_restart_steps_declare_their_restarts():
    """
    The full run declares the restart and the history the restart run starts
    from, and the restart run reads that restart, so a missing one is caught
    before the model launches.
    """
    task = _restart_task()
    full_run = task.steps['full_run']
    full_run._add_restart_files()
    assert RESTART_FILE in full_run.outputs
    assert BEFORE_RESTART_FILENAME in full_run.outputs

    restart_run = task.steps['restart_run']
    restart_run._add_restart_files()
    inputs = [entry['filename'] for entry in restart_run.input_data]
    assert RESTART_FILE in inputs


def test_restart_task_rejects_mpas_ocean():
    step = _restart_task(model='mpas-ocean').steps['restart_run']
    with pytest.raises(ValueError, match='supports only Omega'):
        step.setup()
