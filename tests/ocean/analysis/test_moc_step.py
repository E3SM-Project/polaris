"""
Unit tests for the meridional overturning circulation step.

These run the step over MOC files shaped like the ones Omega's MOC analysis
group writes: monthly means of the streamfunction on latitude bins and layer
interfaces, the bin boundaries beside it, and the horizontally averaged
interface elevation that is the vertical axis, each file named for the month
after the one it averages and carrying the bounds of that month.  What they
check is what the step does with what Omega gave it -- the climatology
``ncclimo`` computes from it, the bin boundaries becoming centers, the
orientation of the field -- and what it does when a simulation predates part
of the capability.
"""

import json
import logging
import os
import shutil

import numpy as np
import pytest
import xarray as xr

from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import add_analysis_tasks
from polaris.tasks.ocean.analysis.moc import (
    DATA_FILENAME,
    INTERFACE_ELEVATION_VARIABLE,
    LAT_BIN_BOUNDARY_VARIABLE,
    PLOT_FILENAME,
    STREAMFUNCTION_VARIABLE,
    _stream_problem,
)
from polaris.tasks.ocean.analysis.sim_files import AnalysisStream

# a coarse version of Omega's defaults: 12 one-degree-ish bins over the globe
# and 8 layer interfaces
N_BINS = 12
N_INTERFACES = 8
BIN_BOUNDARIES = np.linspace(-90.0, 90.0, N_BINS + 1)
INTERFACES = np.linspace(-4000.0, 0.0, N_INTERFACES)

# the noleap calendar the simulation is run on
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# what Omega appends to the streamfunction in a monthly mean
SUFFIX = '_TimeMean1Month'

pytestmark = pytest.mark.skipif(
    shutil.which('ncclimo') is None,
    reason='ncclimo is not on the path',
)


def streamfunction(scale, n_bins=N_BINS, n_interfaces=N_INTERFACES):
    """A two-celled streamfunction on (elevation, latitude), scaled"""
    lat = np.linspace(-90.0, 90.0, n_bins)
    z = np.linspace(-4000.0, 0.0, n_interfaces)
    shape = np.sin(2.0 * np.pi * (lat[np.newaxis, :] + 90.0) / 180.0) * np.sin(
        np.pi * (z[:, np.newaxis] + 4000.0) / 4000.0
    )
    return float(scale) * shape


def monthly_scale(year, month):
    """How strong the synthetic streamfunction is in a given month"""
    return 12.0 * (year - 1) + month


def write_moc_file(
    path,
    first_day,
    last_day,
    values,
    suffix=SUFFIX,
    with_streamfunction=True,
    with_boundaries=True,
    with_elevations=True,
    boundaries=None,
):
    """
    Write one month of MOC output shaped like what Omega's MOC group writes

    Omega stamps a monthly mean with the end of the month and gives its
    bounds, writes the streamfunction with latitude before elevation, and
    writes the bin boundaries without a time dimension.
    """
    ds = xr.Dataset(
        data_vars={'time_bnds': (('time', 'D2'), [[first_day, last_day]])},
        coords={'time': ('time', [last_day])},
    )
    ds.time.attrs = dict(
        units='days since 0001-01-01',
        calendar='noleap',
        bounds='time_bnds',
    )
    if with_streamfunction:
        ds[f'{STREAMFUNCTION_VARIABLE}{suffix}'] = (
            ('time', 'NumBinsLatCell_BinIndex', 'NVertLayersP1'),
            values.transpose()[np.newaxis, :, :],
        )
    if with_boundaries:
        if boundaries is None:
            boundaries = BIN_BOUNDARIES
        ds[LAT_BIN_BOUNDARY_VARIABLE] = (
            ('NMocLatBinBoundaries',),
            np.asarray(boundaries, dtype=float),
        )
    if with_elevations:
        ds[INTERFACE_ELEVATION_VARIABLE] = (
            ('time', 'NVertLayersP1'),
            INTERFACES[np.newaxis, :],
        )
    ds.to_netcdf(path, unlimited_dims=['time'])


def make_step(tmp_path, start_year=1, end_year=1, **options):
    """A moc step wired up as it would be after setup()."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    add_analysis_tasks(component)

    config = component.tasks['analysis/moc'].config
    config.set('ocean', 'model', 'omega', user=True)
    config.set('ocean_analysis', 'simulation_name', 'test_run', user=True)
    for option, value in options.items():
        config.set('ocean_analysis_moc', option, value, user=True)

    step = component.tasks['analysis/moc'].steps['moc']
    step.start_year = start_year
    step.end_year = end_year
    step.work_dir = str(tmp_path)
    step.base_work_dir = str(tmp_path)
    step.config = config
    step.logger = logging.getLogger('test_moc')
    step.has_moc_output = True
    step.stream_problem = None
    step.input_filenames = []
    step.outputs = []
    return step


def add_months(step, years=1, months=12, values=None, **kwargs):
    """
    Write MOC files for the first months of a range of years, named the way
    Omega names them, and give them to the step as setup() would
    """
    day = 0.0
    for year in range(1, years + 1):
        for month in range(1, 13):
            first, last = day, day + DAYS_IN_MONTH[month - 1]
            day = last
            if month > months:
                continue
            # Omega names a monthly mean for the month after the one it covers
            named_year, named_month = year, month + 1
            if named_month > 12:
                named_year, named_month = year + 1, 1
            filename = (
                f'moc_1MonthTimeStats.{named_year:04d}-{named_month:02d}.nc'
            )
            write_moc_file(
                os.path.join(step.work_dir, filename),
                first_day=first,
                last_day=last,
                values=(
                    streamfunction(monthly_scale(year, month))
                    if values is None
                    else values
                ),
                **kwargs,
            )
            step.input_filenames.append(filename)


def run_on_months(tmp_path, years=1, step_options=None, **kwargs):
    """Write years of MOC files, run the step over them, and give it back."""
    step = make_step(tmp_path, end_year=years, **(step_options or {}))
    add_months(step, years=years, **kwargs)
    step.runtime_setup()
    step.run()
    return step


def test_the_plot_and_its_netcdf_are_both_produced(tmp_path):
    step = run_on_months(tmp_path)
    assert sorted(os.path.basename(output) for output in step.outputs) == [
        DATA_FILENAME,
        PLOT_FILENAME,
    ]
    for output in step.outputs:
        assert os.path.exists(output)


def test_outputs_are_in_the_steps_own_work_directory(tmp_path):
    """A step that depends on the process working directory cannot run
    beside another one."""
    step = run_on_months(tmp_path)
    for output in step.outputs:
        assert os.path.dirname(output) == str(tmp_path)


def test_the_netcdf_holds_what_was_plotted(tmp_path):
    step = run_on_months(tmp_path)
    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert sorted(str(name) for name in ds.data_vars) == [
            'latBinCenter',
            'mocStreamfunction',
            'zInterface',
        ]
        assert ds.mocStreamfunction.dims == ('nVertInterfaces', 'nLatBins')
        assert ds.mocStreamfunction.attrs['units'] == 'Sv'
        assert ds.attrs['year_range'] == '0001-0001'
        assert ds.attrs['region'] == 'Global'
        assert ds.attrs['reduction_period'] == '1Month'
        assert ds.attrs['simulation_name'] == 'test_run'


def test_the_latitude_axis_is_bin_centers_not_boundaries(tmp_path):
    """Omega writes the boundaries, one more of them than there are bins;
    contouring is defined at points."""
    step = run_on_months(tmp_path)
    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert ds.sizes['nLatBins'] == N_BINS
        expected = 0.5 * (BIN_BOUNDARIES[:-1] + BIN_BOUNDARIES[1:])
        assert np.allclose(ds.latBinCenter.values, expected)


def test_the_elevation_axis_is_the_one_omega_reported(tmp_path):
    """Polaris plots the interface elevations Omega averaged over the same
    period rather than reconstructing them."""
    step = run_on_months(tmp_path)
    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert np.allclose(ds.zInterface.values, INTERFACES)
        assert ds.zInterface.attrs['units'] == 'm'


def test_the_annual_mean_weights_each_month_by_its_length(tmp_path):
    """The streamfunction is linear in the velocity, so a mean weighted by
    the length of each month is the streamfunction of the mean flow.  The
    first month counts for its own 31 days, whatever the gap between the time
    stamps before it would suggest, and each year counts once."""
    years = 2
    step = run_on_months(tmp_path, years=years)
    days = np.array(DAYS_IN_MONTH, dtype=float)
    scales = np.array(
        [
            [monthly_scale(year, month) for month in range(1, 13)]
            for year in range(1, years + 1)
        ]
    )
    weighted = np.sum(days * scales.mean(axis=0)) / np.sum(days)

    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        # the field is a fixed shape times a monthly scale, so the average is
        # the weighted mean of the scales times that shape
        shape = streamfunction(1.0)
        assert np.allclose(ds.mocStreamfunction.values, weighted * shape)
        assert not np.allclose(
            ds.mocStreamfunction.values, scales.mean() * shape
        )


def test_the_variable_a_reduction_writes_is_the_one_read(tmp_path, caplog):
    """A time reduction adds a _TimeMean<period> suffix to the
    streamfunction and leaves the coordinate fields alone."""
    with caplog.at_level(logging.INFO):
        run_on_months(tmp_path)
    assert f'{STREAMFUNCTION_VARIABLE}{SUFFIX}' in caplog.text
    assert f'read {LAT_BIN_BOUNDARY_VARIABLE}' in caplog.text
    assert f'read {INTERFACE_ELEVATION_VARIABLE}' in caplog.text


@pytest.mark.parametrize(
    'stream',
    [
        AnalysisStream('moc_1MonthInstants.$Y-$M.nc', '1Month', False),
        AnalysisStream('moc_1YearTimeStats.$Y.nc', '1Year', True),
        AnalysisStream('moc_1MonthTimeStats.nc', '1Month', True),
    ],
)
def test_output_that_is_not_monthly_means_is_reported(stream):
    """ncclimo computes the climatology from one file of monthly means per
    month, so snapshots, other periods and a single file are reported as
    what the group would need to write instead."""
    problem = _stream_problem(stream)
    assert problem is not None
    assert stream.filename in problem
    assert 'ReductionPeriod: [1Month]' in problem


def test_monthly_means_in_monthly_files_can_be_averaged():
    stream = AnalysisStream('moc_1MonthTimeStats.$Y-$M.nc', '1Month', True)
    assert _stream_problem(stream) is None


def test_output_that_cannot_be_averaged_makes_nothing(tmp_path, caplog):
    step = make_step(tmp_path)
    step.stream_problem = 'the MOC group writes snapshots'
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert 'the MOC group writes snapshots' in caplog.text
    assert _manifest_products(step) == []


def test_a_simulation_that_wrote_no_moc_output_makes_nothing(tmp_path, caplog):
    """Omega's MOC diagnostic is new, so a simulation without it is an
    ordinary case rather than a failed step."""
    step = make_step(tmp_path)
    step.has_moc_output = False
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert 'MOC analysis group' in caplog.text
    assert _manifest_products(step) == []


def test_moc_output_without_elevations_is_reported_not_a_traceback(
    tmp_path, caplog
):
    """Interface elevations came later than the streamfunction, so a file
    with one and not the other will be met.  Polaris does not reconstruct
    them, so it says what is missing and what would have written it."""
    step = make_step(tmp_path)
    add_months(step, with_elevations=False)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert INTERFACE_ELEVATION_VARIABLE in caplog.text
    assert 'elevation axis' in caplog.text
    assert _manifest_products(step) == []


def test_moc_output_without_latitude_bins_is_reported(tmp_path, caplog):
    step = make_step(tmp_path)
    add_months(step, with_boundaries=False)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert 'latitude axis' in caplog.text


def test_a_file_without_the_streamfunction_names_what_is_there(
    tmp_path, caplog
):
    step = make_step(tmp_path)
    add_months(step, with_streamfunction=False)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert STREAMFUNCTION_VARIABLE in caplog.text
    assert LAT_BIN_BOUNDARY_VARIABLE in caplog.text


def test_a_streamfunction_that_matches_neither_axis_is_an_error(tmp_path):
    """A file whose three fields do not belong together -- bin boundaries
    for a different number of bins than the streamfunction was binned into --
    would otherwise be plotted as whatever the shapes happened to allow."""
    step = make_step(tmp_path)
    add_months(step, boundaries=np.linspace(-90.0, 90.0, 6))
    step.runtime_setup()
    with pytest.raises(ValueError, match='do not match'):
        step.run()


def test_the_manifest_describes_the_plot(tmp_path):
    """The gallery is a group per product and a gallery per region, so that
    regional overturning adds galleries here rather than a group."""
    step = run_on_months(tmp_path)
    products = _manifest_products(step)
    assert len(products) == 1
    product = products[0]
    assert product['plot'] == PLOT_FILENAME
    assert product['data'] == DATA_FILENAME
    assert product['group'] == 'moc'
    assert product['gallery'] == 'global'
    assert product['region'] == 'Global'
    assert product['start_year'] == 1
    assert product['end_year'] == 1


def _manifest_products(step):
    """What the step said it made, as the publish step reads it"""
    with open(step.work_path(FRAGMENT_FILENAME)) as fragment:
        return json.load(fragment)['products']
