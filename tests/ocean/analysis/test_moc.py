"""
Unit tests for the meridional overturning circulation step.

These run the step over MOC files shaped like the ones Omega's MOC analysis
group writes: the streamfunction on latitude bins and layer interfaces, the
bin boundaries beside it, and the horizontally averaged interface elevation
that is the vertical axis.  What they check is the arithmetic the step does to
what Omega gave it -- the weighting of the time average, the bin boundaries
becoming centers, the orientation of the field -- and what it does when a
simulation predates part of the capability.
"""

import json
import logging
import os

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
    period_lengths,
)

# a coarse version of Omega's defaults: 12 one-degree-ish bins over the globe
# and 8 layer interfaces
N_BINS = 12
N_INTERFACES = 8
BIN_BOUNDARIES = np.linspace(-90.0, 90.0, N_BINS + 1)
INTERFACES = np.linspace(-4000.0, 0.0, N_INTERFACES)


def streamfunction(month, n_bins=N_BINS, n_interfaces=N_INTERFACES):
    """A two-celled streamfunction whose amplitude varies with the month"""
    lat = np.linspace(-90.0, 90.0, n_bins)
    z = np.linspace(-4000.0, 0.0, n_interfaces)
    shape = np.sin(2.0 * np.pi * (lat[np.newaxis, :] + 90.0) / 180.0) * np.sin(
        np.pi * (z[:, np.newaxis] + 4000.0) / 4000.0
    )
    return float(month) * shape


def write_moc_file(
    path,
    year,
    month,
    period='1Month',
    with_boundaries=True,
    with_elevations=True,
    values=None,
    boundaries=None,
):
    """Write a MOC file shaped like the ones Omega's MOC group writes."""
    time = xr.date_range(
        start=f'{year:04d}-{month:02d}-01',
        periods=1,
        freq='D',
        calendar='noleap',
        use_cftime=True,
    )
    ds = xr.Dataset(coords={'time': ('time', time)})
    if values is None:
        values = streamfunction(month)
    suffix = '' if period is None else f'_TimeMean{period}'
    ds[f'{STREAMFUNCTION_VARIABLE}{suffix}'] = (
        ('time', 'NVertLayersP1', 'NumBinsLatCell_BinIndex'),
        values[np.newaxis, :, :],
    )
    if with_boundaries:
        if boundaries is None:
            boundaries = BIN_BOUNDARIES
        boundaries = np.asarray(boundaries, dtype=float)
        # Omega attaches the bin boundaries to the output stream like any
        # other field, so they carry a time dimension even though they are
        # static
        ds[LAT_BIN_BOUNDARY_VARIABLE] = (
            ('time', 'NMocLatBinBoundaries'),
            boundaries[np.newaxis, :],
        )
    if with_elevations:
        ds[INTERFACE_ELEVATION_VARIABLE] = (
            ('time', 'NVertLayersP1'),
            INTERFACES[np.newaxis, :],
        )
    ds.to_netcdf(path)


def make_step(tmp_path, start_year=1, end_year=1, period='1Month', **options):
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
    step.reduction_period = period
    step.input_filenames = []
    step.outputs = []
    return step


def run_on_months(tmp_path, months=12, year=1, **kwargs):
    """Write a year of MOC files, run the step over them, and give it back."""
    step = make_step(tmp_path, **kwargs.pop('step_options', {}))
    for month in range(1, months + 1):
        filename = f'moc_1MonthTimeStats.{year:04d}-{month:02d}.nc'
        write_moc_file(
            os.path.join(str(tmp_path), filename),
            year=year,
            month=month,
            **kwargs,
        )
        step.input_filenames.append(filename)
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


def test_bin_boundaries_repeated_every_month_give_one_latitude_axis(tmp_path):
    """Omega writes the bin boundaries into every reduction, so a range of
    twelve months carries twelve identical copies.  Flattening them would
    give twelve times as many latitudes as there are bins."""
    step = run_on_months(tmp_path)
    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert ds.sizes['nLatBins'] == N_BINS


def test_bin_boundaries_that_disagree_between_months_are_an_error(tmp_path):
    """Two simulations mixed into one range would otherwise be averaged into
    a streamfunction whose latitude axis belongs to neither."""
    step = make_step(tmp_path)
    for month in (1, 2):
        filename = f'moc_1MonthTimeStats.0001-{month:02d}.nc'
        write_moc_file(
            os.path.join(str(tmp_path), filename),
            year=1,
            month=month,
            boundaries=(
                BIN_BOUNDARIES if month == 1 else BIN_BOUNDARIES * 0.5
            ),
        )
        step.input_filenames.append(filename)
    step.runtime_setup()
    with pytest.raises(ValueError, match='changes over the range'):
        step.run()


def test_the_elevation_axis_is_the_one_omega_reported(tmp_path):
    """Polaris plots the interface elevations Omega averaged over the same
    period rather than reconstructing them."""
    step = run_on_months(tmp_path)
    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert np.allclose(ds.zInterface.values, INTERFACES)
        assert ds.zInterface.attrs['units'] == 'm'


def test_the_time_average_is_weighted_by_the_length_of_each_period(tmp_path):
    """The streamfunction is linear in the velocity, so a mean weighted by
    the length of each reduction is the streamfunction of the mean flow.  The
    months of a noleap year are not the same length, so an unweighted mean is
    a different number."""
    step = run_on_months(tmp_path)
    days = np.array([31, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30], float)
    months = np.arange(1.0, 13.0)
    weighted = np.sum(days * months) / np.sum(days)

    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        # the field is the month times a fixed shape, so the average is the
        # weighted mean of the months times that shape
        shape = streamfunction(1.0)
        assert np.allclose(ds.mocStreamfunction.values, weighted * shape)
        assert not np.allclose(
            ds.mocStreamfunction.values, months.mean() * shape
        )


def test_period_lengths_are_the_gaps_between_the_stamps(tmp_path):
    """Omega stamps a reduction with one time rather than with the bounds of
    the period, so the length of a period is the gap to the next stamp, and
    the first is given the length of the second."""
    time = xr.date_range(
        start='0001-01-01',
        periods=4,
        freq='MS',
        calendar='noleap',
        use_cftime=True,
    )
    ds = xr.Dataset(coords={'Time': ('Time', time)})
    assert np.allclose(period_lengths(ds), [31.0, 31.0, 28.0, 31.0])


def test_reductions_that_do_not_step_forward_are_an_error(tmp_path):
    """Equal time stamps give zero weights, and a weighted mean by zero
    weights is NaN rather than an error -- a published plot of NaN is the one
    outcome worse than a failed step."""
    time = xr.date_range(
        start='0001-01-01',
        periods=3,
        freq='MS',
        calendar='noleap',
        use_cftime=True,
    )
    repeated = xr.Dataset(coords={'Time': ('Time', [time[0]] * 3)})
    with pytest.raises(ValueError, match='does not step forward in time'):
        period_lengths(repeated)


def test_a_single_reduction_needs_no_weight(tmp_path):
    """One reduction carries the whole average, so its weight cancels."""
    time = xr.date_range(
        start='0001-01-01',
        periods=1,
        freq='MS',
        calendar='noleap',
        use_cftime=True,
    )
    ds = xr.Dataset(coords={'Time': ('Time', time)})
    assert np.allclose(period_lengths(ds), [1.0])


def test_snapshots_are_averaged_with_equal_weights(tmp_path, caplog):
    """Snapshots cover no period, so there is no period to weight by."""
    step = make_step(tmp_path, period=None)
    for month in range(1, 4):
        filename = f'moc_1DayInstants.0001-{month:02d}.nc'
        write_moc_file(
            os.path.join(str(tmp_path), filename),
            year=1,
            month=month,
            period=None,
        )
        step.input_filenames.append(filename)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    with xr.open_dataset(step.work_path(DATA_FILENAME)) as ds:
        assert np.allclose(
            ds.mocStreamfunction.values, 2.0 * streamfunction(1.0)
        )
        assert ds.attrs['reduction_period'] == 'none; these are snapshots'
    assert 'equal weights' in caplog.text


def test_the_variable_a_reduction_writes_is_the_one_read(tmp_path, caplog):
    """A time reduction adds a _TimeMean<period> suffix to the
    streamfunction and leaves the coordinate fields alone."""
    with caplog.at_level(logging.INFO):
        run_on_months(tmp_path, months=1)
    assert f'{STREAMFUNCTION_VARIABLE}_TimeMean1Month' in caplog.text
    assert f'read {LAT_BIN_BOUNDARY_VARIABLE}' in caplog.text
    assert f'read {INTERFACE_ELEVATION_VARIABLE}' in caplog.text


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
    filename = 'moc_1MonthTimeStats.0001-01.nc'
    write_moc_file(
        os.path.join(str(tmp_path), filename),
        year=1,
        month=1,
        with_elevations=False,
    )
    step.input_filenames.append(filename)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert INTERFACE_ELEVATION_VARIABLE in caplog.text
    assert 'elevation axis' in caplog.text
    assert _manifest_products(step) == []


def test_moc_output_without_latitude_bins_is_reported(tmp_path, caplog):
    step = make_step(tmp_path)
    filename = 'moc_1MonthTimeStats.0001-01.nc'
    write_moc_file(
        os.path.join(str(tmp_path), filename),
        year=1,
        month=1,
        with_boundaries=False,
    )
    step.input_filenames.append(filename)
    step.runtime_setup()
    with caplog.at_level(logging.INFO):
        step.run()

    assert not os.path.exists(step.work_path(PLOT_FILENAME))
    assert 'latitude axis' in caplog.text


def test_a_file_without_the_streamfunction_names_what_is_there(
    tmp_path, caplog
):
    step = make_step(tmp_path)
    filename = 'moc_1MonthTimeStats.0001-01.nc'
    time = xr.date_range(
        start='0001-01-01',
        periods=1,
        freq='D',
        calendar='noleap',
        use_cftime=True,
    )
    ds = xr.Dataset(coords={'time': ('time', time)})
    ds[LAT_BIN_BOUNDARY_VARIABLE] = (
        ('time', 'NMocLatBinBoundaries'),
        BIN_BOUNDARIES[np.newaxis, :],
    )
    ds[INTERFACE_ELEVATION_VARIABLE] = (
        ('time', 'NVertLayersP1'),
        INTERFACES[np.newaxis, :],
    )
    ds.to_netcdf(os.path.join(str(tmp_path), filename))
    step.input_filenames.append(filename)
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
    filename = 'moc_1MonthTimeStats.0001-01.nc'
    write_moc_file(
        os.path.join(str(tmp_path), filename),
        year=1,
        month=1,
        boundaries=np.linspace(-90.0, 90.0, 6),
    )
    step.input_filenames.append(filename)
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
