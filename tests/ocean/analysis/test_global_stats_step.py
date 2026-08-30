import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.model.time import days_per_year
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import add_analysis_tasks
from polaris.tasks.ocean.analysis.sim_files import AnalysisStream, OmegaConfig

# what the QU240 mock-up writes: snapshots of six fields, four statistics
# each, on a time axis of daily values in a noleap calendar
MOCKUP_FIELDS = [
    'Temperature',
    'Salinity',
    'NormalVelocity',
    'KineticEnergyCell',
    'SshCell',
    'PseudoThickness',
]
MOCKUP_STATS = ['SpatialMean', 'SpatialMin', 'SpatialMax', 'SpatialStdDev']


def write_stats_file(path, fields=None, stats=None, days=730):
    """Write a global statistics file shaped like the ones Omega writes."""
    if fields is None:
        fields = MOCKUP_FIELDS
    if stats is None:
        stats = MOCKUP_STATS

    time = xr.date_range(
        start='0001-01-01',
        periods=days,
        freq='D',
        calendar='noleap',
        use_cftime=True,
    )
    ds = xr.Dataset(coords={'time': ('time', time)})
    values = np.linspace(0.0, 1.0, days)
    for index, field in enumerate(fields):
        for stat in stats:
            ds[f'{field}_{stat}'] = (
                ('time', 'Scalar'),
                (values + index)[:, np.newaxis],
            )
            ds[f'{field}_{stat}'].attrs['units'] = 'degC'
    ds.to_netcdf(path)


def make_step(tmp_path, start_year=1, end_year=2, **options):
    """A global_stats step wired up as it would be after setup()."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    add_analysis_tasks(component)

    config = component.tasks['analysis/global_stats'].config
    config.set('ocean', 'model', 'omega', user=True)
    config.set('ocean_analysis', 'simulation_name', 'test_run', user=True)
    for option, value in options.items():
        config.set('ocean_analysis_time_series', option, value, user=True)

    step = component.tasks['analysis/global_stats'].steps['global_stats']
    step.start_year = start_year
    step.end_year = end_year
    step.work_dir = str(tmp_path)
    step.base_work_dir = str(tmp_path)
    step.config = config
    step.logger = logging.getLogger('test_global_stats_step')
    step.input_filenames = ['global_stats_1DayInstants']
    step.outputs = []
    return step


def run_on_a_file(tmp_path, fields=None, stats=None, fields_asked=None):
    """Write a statistics file, run the step over it, and return the step."""
    options = {} if fields_asked is None else {'fields': fields_asked}
    step = make_step(tmp_path, **options)
    write_stats_file(
        os.path.join(str(tmp_path), 'global_stats_1DayInstants'),
        fields=fields,
        stats=stats,
    )
    step.run()
    return step


def test_a_netcdf_is_registered_beside_every_plot(tmp_path):
    """The data behind a plot is a product, so it is declared like one."""
    step = run_on_a_file(tmp_path, fields=['Temperature', 'SshCell'])

    plots = sorted(o for o in step.outputs if o.endswith('.png'))
    data = sorted(o for o in step.outputs if o.endswith('.nc'))
    assert len(plots) == 2
    assert [f'{os.path.splitext(o)[0]}.nc' for o in plots] == data
    for output in step.outputs:
        assert os.path.exists(output)


def test_outputs_are_in_the_steps_own_work_directory(tmp_path):
    """A step that depends on the process working directory cannot run
    beside another one."""
    step = run_on_a_file(tmp_path, fields=['Temperature'])
    for output in step.outputs:
        assert os.path.dirname(output) == str(tmp_path)


def test_the_netcdf_holds_what_was_plotted(tmp_path):
    step = run_on_a_file(tmp_path, fields=['Temperature'])
    filename = next(o for o in step.outputs if o.endswith('.nc'))

    with xr.open_dataset(filename) as ds:
        # data_vars keys are Hashable, not str, so sort the names
        assert sorted(str(name) for name in ds.data_vars) == [
            'max',
            'mean',
            'min',
            'simulationYears',
            'std',
        ]
        assert ds.attrs['field'] == 'temperature'
        assert ds.attrs['simulation_name'] == 'test_run'
        assert ds.attrs['start_year'] == step.start_year
        assert ds.attrs['end_year'] == step.end_year
        assert ds['mean'].attrs['omega_name'] == 'Temperature_SpatialMean'
        assert ds['mean'].attrs['units'] == 'degC'


def test_the_time_axis_is_in_simulation_years(tmp_path):
    """Two years of daily values span two years of a noleap calendar."""
    step = run_on_a_file(tmp_path, fields=['Temperature'])
    filename = next(o for o in step.outputs if o.endswith('.nc'))

    with xr.open_dataset(filename) as ds:
        years = ds['simulationYears'].values
        assert ds['simulationYears'].attrs['units'] == 'years'
    # the file starts on the first day of year 1 and runs for 730 days
    assert years[0] == pytest.approx(1.0)
    assert years[-1] - years[0] == pytest.approx(
        729.0 / days_per_year('noleap')
    )


def test_a_field_the_simulation_did_not_write_is_skipped(tmp_path):
    """The default list describes what we would like, not what a run wrote."""
    step = run_on_a_file(
        tmp_path,
        fields=['Temperature', 'SshCell'],
        fields_asked='temperature, salinity, ssh',
    )
    plotted = sorted(
        os.path.basename(o) for o in step.outputs if o.endswith('.png')
    )
    assert plotted == ['ssh.png', 'temperature.png']


def test_a_statistic_the_simulation_did_not_write_is_skipped(tmp_path):
    step = run_on_a_file(
        tmp_path,
        fields=['Temperature'],
        stats=['SpatialMean', 'SpatialMax'],
    )
    filename = next(o for o in step.outputs if o.endswith('.nc'))
    with xr.open_dataset(filename) as ds:
        assert sorted(ds.attrs['statistics'].split(', ')) == ['max', 'mean']


def test_nothing_the_step_asked_for_present_raises(tmp_path):
    """Usually the year range is wrong, which is worth interrupting for."""
    with pytest.raises(ValueError, match='years 1 through 2'):
        run_on_a_file(
            tmp_path,
            fields=['Salinity'],
            fields_asked='temperature, ssh',
        )


def test_an_empty_field_list_plots_what_the_simulation_wrote(tmp_path):
    step = run_on_a_file(
        tmp_path,
        fields=['Temperature', 'KineticEnergyCell', 'PseudoThickness'],
        fields_asked='',
    )
    plotted = sorted(
        os.path.basename(o) for o in step.outputs if o.endswith('.png')
    )
    assert plotted == [
        'PseudoThickness.png',
        'kineticEnergyCell.png',
        'temperature.png',
    ]


def test_a_time_mean_stream_is_read_with_the_time_mean_names(tmp_path):
    """A reduction spells its variables with the period in the name."""
    step = make_step(tmp_path)
    step.time_mean_period = '1Month'
    write_stats_file(
        os.path.join(str(tmp_path), 'global_stats_1DayInstants'),
        fields=['Temperature'],
        stats=['SpatialMean_TimeMean1Month'],
    )
    step.run()

    filename = next(o for o in step.outputs if o.endswith('.nc'))
    with xr.open_dataset(filename) as ds:
        assert (
            ds['mean'].attrs['omega_name']
            == 'Temperature_SpatialMean_TimeMean1Month'
        )
        assert ds.attrs['time_mean_period'] == '1Month'


def test_the_stream_says_whether_it_is_a_reduction():
    """setup() needs the stream, not just the file name it supplies."""
    omega_config = OmegaConfig(
        filename='omega.yml',
        streams={},
        options={
            'Analysis': {
                'GlobalStats': {
                    'Enable': True,
                    'Filename': 'global_stats',
                    'ReductionPeriod': [],
                    'SnapshotPeriod': ['1Day'],
                }
            }
        },
    )
    streams = omega_config.analysis_streams('GlobalStats')
    assert streams == [
        AnalysisStream(
            filename='global_stats_1DayInstants',
            period='1Day',
            is_reduction=False,
        )
    ]
