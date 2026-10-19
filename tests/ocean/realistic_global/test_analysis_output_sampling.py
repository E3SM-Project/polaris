import numpy as np
import pytest

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.analysis_output.sampling import (
    SAMPLING_STEPS,
    get_sampling_mean_filenames,
)
from polaris.tasks.ocean.realistic_global.analysis_output.sampling_analysis import (  # noqa: E501
    fit_order,
    relative_l2_error,
    relative_max_difference,
    select_period,
)
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
from polaris.yaml import PolarisYaml

TASK_SUBDIR = (
    'spherical/realistic_global/e3sm-qu240/analysis_output/'
    'sampling_convergence'
)
PACKAGE = 'polaris.tasks.ocean.realistic_global.analysis_output'


def _sampling_task(model='omega'):
    """The registered task, with its config combined for ``model``"""
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


def test_sampling_task_is_registered_on_the_cached_qu240():
    task = _sampling_task()
    assert list(task.steps) == [
        'reference',
        'sampled_2_steps',
        'sampled_4_steps',
        'sampled_8_steps',
        'sampled_16_steps',
        'analysis',
    ]
    inputs = [entry['filename'] for entry in task.steps['analysis'].input_data]
    assert 'snapshots.nc' in inputs
    for filename in get_sampling_mean_filenames():
        assert f'reference_{filename}' in inputs
        assert f'sampled_16_steps_{filename}' in inputs


def test_sampling_mean_filenames_are_named_for_the_period_ends():
    assert get_sampling_mean_filenames() == [
        'means_1DayTimeStats.0001-01-02.nc',
        'means_1DayTimeStats.0001-01-03.nc',
    ]


@pytest.mark.parametrize(
    'name, sampling_interval, output_freq',
    [
        ('reference', 'dt', '172800'),
        ('sampled_2_steps', '2steps', '172800'),
        ('sampled_8_steps', '8steps', '172800'),
        # the coarsest sampling writes a snapshot at every sample
        ('sampled_16_steps', '16steps', '9600'),
    ],
)
def test_sampled_runs_use_rk4_and_their_sampling_interval(
    name, sampling_interval, output_freq
):
    step = _sampling_task().steps[name]
    step.dynamic_model_config(at_setup=True)

    replacements = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.forward', 'forward.yaml'
    )
    assert replacements['time_integrator'] == 'RungeKutta4'
    assert replacements['dt'] == '00:10:00'
    assert replacements['run_duration'] == '0002_00:00:00'
    assert replacements['output_freq'] == output_freq

    analysis = _model_config_entry(step, PACKAGE, 'sampling_analysis.yaml')
    assert analysis['sampling_interval'] == sampling_interval
    assert analysis['period'] == '1Day'

    yaml = PolarisYaml.read(
        filename='sampling_analysis.yaml',
        package=PACKAGE,
        replacements=analysis,
        model='Omega',
        streams_section='IOStreams',
    )
    fields = ['Temperature', 'Salinity', 'NormalVelocity', 'PseudoThickness']
    means = yaml.configs['Analysis']['MonthlyAverages']
    assert means['Fields'] == fields
    assert means['SamplingInterval'] == sampling_interval
    assert yaml.streams['History']['Contents'] == fields


def test_every_sampling_interval_divides_the_period():
    """Omega aborts unless the sampling interval divides the period"""
    task = _sampling_task()
    stage = ForwardStage.from_config(task.config)
    dt = stage.time_step_seconds(model='omega', min_res=240.0)
    for steps in SAMPLING_STEPS:
        assert 86400.0 % (steps * dt) == 0.0


def test_time_step_seconds_follows_the_time_integrator():
    task = _sampling_task()
    stage = ForwardStage.from_config(task.config)
    assert stage.time_step_seconds(model='omega', min_res=240.0) == 600.0
    split = ForwardStage(dt='01:00:00', btr_dt='00:03:00')
    assert split.time_step_seconds(model='omega', min_res=240.0) == 3600.0


def test_sampling_task_rejects_mpas_ocean():
    step = _sampling_task(model='mpas-ocean').steps['reference']
    with pytest.raises(ValueError, match='supports only Omega'):
        step.setup()


def test_fit_order_recovers_first_order():
    intervals = np.array([1.0, 3.0, 7.0, 15.0])
    assert fit_order(intervals, 2.0e-4 * intervals) == pytest.approx(1.0)
    assert fit_order(intervals, 5.0 * intervals**2) == pytest.approx(2.0)


def test_fit_order_rejects_a_zero_error():
    with pytest.raises(ValueError, match='not all positive'):
        fit_order(np.array([1.0, 3.0]), np.array([0.0, 1.0]))


def test_relative_l2_error_skips_inactive_layers():
    reference = np.array([3.0, 4.0, np.nan])
    values = np.array([3.0, 4.5, 1.0e36])
    assert relative_l2_error(values, reference) == pytest.approx(0.1)


def test_select_period_excludes_the_start_and_includes_the_end():
    times = np.array([0.0, 9600.0, 86400.0, 96000.0])
    assert list(select_period(times, 0.0, 86400.0)) == [
        False,
        True,
        True,
        False,
    ]


def test_relative_max_difference_skips_inactive_layers():
    reference = np.array([2.0, -4.0, np.nan])
    values = np.array([2.0, -4.0 + 4.0e-12, 7.0])
    assert relative_max_difference(values, reference) == pytest.approx(1e-12)
