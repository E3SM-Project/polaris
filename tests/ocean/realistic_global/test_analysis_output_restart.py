import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.analysis_output.restart import (
    get_analysis_restart_filenames,
)
from polaris.tasks.ocean.realistic_global.analysis_output.restart_validate import (  # noqa: E501
    compare_datasets_exactly,
)
from polaris.yaml import PolarisYaml

TASK_SUBDIR = 'spherical/realistic_global/e3sm-qu240/analysis_output/restart'
PACKAGE = 'polaris.tasks.ocean.realistic_global.analysis_output'


def _restart_task(model='omega'):
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


def _output_filenames(step):
    return step.outputs


def test_analysis_restart_filenames_are_named_for_the_period_ends():
    assert get_analysis_restart_filenames() == [
        'means_2DaysTimeStats.0001-01-03.nc',
        'moc_2DaysTimeStats.0001-01-03.nc',
        'means_2DaysTimeStats.0001-01-05.nc',
        'moc_2DaysTimeStats.0001-01-05.nc',
        'global_stats_2DaysTimeStats',
    ]


def test_analysis_restart_task_is_registered_on_the_cached_qu240():
    task = _restart_task()
    assert list(task.steps) == ['full_run', 'restart_run', 'validate']
    filenames = get_analysis_restart_filenames()

    # both runs reach the end of the periods, so both declare every time mean
    for name in ['full_run', 'restart_run']:
        outputs = _output_filenames(task.steps[name])
        assert set(filenames) <= set(outputs)

    inputs = [entry['filename'] for entry in task.steps['validate'].input_data]
    for filename in filenames:
        assert f'full_run_{filename}' in inputs
        assert f'restart_run_{filename}' in inputs


@pytest.mark.parametrize(
    'name, run_duration, overlay_yaml',
    [
        ('full_run', '0004_00:00:00', 'full_run.yaml'),
        ('restart_run', '0003_00:00:00', 'restart_run.yaml'),
    ],
)
def test_analysis_restart_steps_split_the_first_period(
    name, run_duration, overlay_yaml
):
    """
    The full run covers two 2-day periods and writes a restart one day in,
    halfway through the first, which the restart run continues from, with
    every group averaging over the same period and each sampling in its own
    way
    """
    step = _restart_task().steps[name]
    step.dynamic_model_config(at_setup=True)

    replacements = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.forward', 'forward.yaml'
    )
    assert replacements['time_integrator'] == 'SplitExplicitRK2'
    assert replacements['run_duration'] == run_duration

    overlay = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.restart', overlay_yaml
    )
    if name == 'full_run':
        # a restart every day, so one at the restart time
        assert overlay['restart_freq'] == '86400'
    else:
        assert overlay['restart_read_file'] == (
            '../restarts/full_run/ocn.restart.0001-01-02_00.00.00.nc'
        )

    analysis = _model_config_entry(step, PACKAGE, 'restart_analysis.yaml')
    assert analysis == dict(
        period='2Days',
        file_freq_days=2,
        moc_num_bins=60,
        moc_sampling_interval='3perPeriod',
        stats_sampling_interval='6hour',
    )

    yaml = PolarisYaml.read(
        filename='restart_analysis.yaml',
        package=PACKAGE,
        replacements=analysis,
        model='Omega',
        streams_section='IOStreams',
    )
    groups = yaml.configs['Analysis']
    for group in ['GlobalStats', 'MonthlyAverages', 'MOC']:
        assert groups[group]['ReductionPeriod'] == ['2Days']
    assert groups['MonthlyAverages']['SamplingInterval'] == 'dt'
    assert groups['MOC']['SamplingInterval'] == '3perPeriod'
    assert groups['GlobalStats']['SamplingInterval'] == '6hour'
    assert groups['MOC']['Stream']['FileFreq'] == 2


def test_analysis_restart_task_rejects_mpas_ocean():
    step = _restart_task(model='mpas-ocean').steps['full_run']
    with pytest.raises(ValueError, match='supports only Omega'):
        step.setup()


def test_analysis_restart_task_rejects_another_start_time():
    """The time-mean file names assume the runs start on 0001-01-01"""
    task = _restart_task()
    task.config.set(
        'realistic_global_forward', 'start_time', '0001-02-01_00:00:00'
    )
    with pytest.raises(ValueError, match='needs start_time'):
        task.steps['full_run'].dynamic_model_config(at_setup=True)


def _dataset(values, time=0.0):
    return xr.Dataset(
        dict(
            Temperature_TimeMean2Days=(('time', 'NCells'), [values]),
            time=(('time',), [time]),
        )
    )


def test_compare_datasets_exactly_passes_identical_datasets():
    values = np.array([1.0, 2.0, np.nan, 9.96920996838687e36])
    assert compare_datasets_exactly(_dataset(values), _dataset(values)) == []


def test_compare_datasets_exactly_reports_differences():
    values = np.array([1.0, 2.0, 3.0])
    other = values.copy()
    other[1] += 1.0e-15
    mismatches = compare_datasets_exactly(
        _dataset(values), _dataset(other, time=1.0)
    )
    assert len(mismatches) == 2
    assert mismatches[0].startswith('Temperature_TimeMean2Days differs at 1')
    assert mismatches[1].startswith('time differs at 1')


def test_compare_datasets_exactly_compares_bits_not_values():
    """Signed zeros and NaNs with other payloads are equal but not BFB"""
    other_nan = np.array([0x7FF8000000000001], dtype=np.uint64).view(
        np.float64
    )[0]
    values = np.array([0.0, np.nan, 1.0])
    other = np.array([-0.0, other_nan, 1.0])
    mismatches = compare_datasets_exactly(_dataset(values), _dataset(other))
    assert len(mismatches) == 1
    assert mismatches[0].startswith(
        'Temperature_TimeMean2Days differs at 2 of 3 points'
    )


def test_compare_datasets_exactly_reports_a_dtype_change():
    ds = _dataset(np.array([1.0, 2.0]))
    other = ds.copy()
    name = 'Temperature_TimeMean2Days'
    other[name] = other[name].astype(np.float32)
    assert compare_datasets_exactly(ds, other) == [
        f'{name} has dtype float64 and float32'
    ]


def test_compare_datasets_exactly_reports_missing_variables():
    ds = _dataset(np.array([1.0]))
    mismatches = compare_datasets_exactly(ds, ds.drop_vars('time'))
    assert mismatches == ['time is only in the first dataset']
