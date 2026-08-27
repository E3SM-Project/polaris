"""
Validate the ``ncclimo`` invocation of the climatology step.

A synthetic monthly-mean data set with Omega names and CF time metadata is
run through the step, and the resulting climatologies are compared against
day-weighted means computed here.  What this tests is our invocation --- the
seasonally discontinuous December convention, the day weighting, and the
claim that ``ncclimo`` reads Omega-style files without ``-P mpaso`` --- and
not ``ncclimo`` itself.
"""

import logging
import shutil

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis.climatology import (
    Climatology,
    find_climatology_file,
)

# the noleap calendar the simulation is run on
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

START_YEAR = 1
END_YEAR = 3

N_CELLS = 4
N_LEVELS = 3

SEASON_MONTHS = {
    'ANN': list(range(1, 13)),
    'DJF': [12, 1, 2],
    'MAM': [3, 4, 5],
    'JJA': [6, 7, 8],
    'SON': [9, 10, 11],
}

pytestmark = pytest.mark.skipif(
    shutil.which('ncclimo') is None,
    reason='ncclimo is not on the path',
)


def monthly_mean(year, month):
    """The value of the synthetic field in a given month, before offsets"""
    return 10.0 * year + month


def test_the_monthly_climatologies_are_means_over_the_years(climatology):
    """Each month's climatology is the unweighted mean over the years."""
    for month in range(1, 13):
        expected = np.mean(
            [
                monthly_mean(year, month)
                for year in range(START_YEAR, END_YEAR + 1)
            ]
        )
        _assert_field(climatology, f'{month:02d}', expected)


def test_the_seasons_are_day_weighted(climatology):
    """Every season, including the annual mean, weights each month by its
    length in the simulation's calendar."""
    for season, months in SEASON_MONTHS.items():
        _assert_field(climatology, season, _day_weighted(months))


def test_december_comes_from_the_same_year_as_january(climatology):
    """The seasonally discontinuous December convention: every year in the
    range contributes exactly one December and no data outside the range are
    needed.  This used to be ``-a sdd`` and is now ncclimo's behavior, so it
    is worth pinning."""
    # under the other convention DJF would draw on a December from the year
    # before the range, which does not exist here, so the two differ
    discontinuous = _day_weighted([12, 1, 2])
    continuous = (
        31.0 * np.mean([monthly_mean(year, 12) for year in (0, 1, 2)])
        + 31.0 * np.mean([monthly_mean(year, 1) for year in (1, 2, 3)])
        + 28.0 * np.mean([monthly_mean(year, 2) for year in (1, 2, 3)])
    ) / 90.0
    assert not np.isclose(discontinuous, continuous)
    _assert_field(climatology, 'DJF', discontinuous)


def test_a_month_can_be_found_by_its_name(climatology):
    """``plot_seasons`` names months JAN through DEC; ncclimo names its files
    by month number."""
    assert find_climatology_file(climatology, 'JAN') == find_climatology_file(
        climatology, '01'
    )


def test_a_season_that_was_not_computed_is_reported(climatology):
    with pytest.raises(FileNotFoundError, match='No climatology for season'):
        find_climatology_file(climatology, 'XYZ')


def test_a_variable_the_simulation_did_not_write_is_left_out(climatology):
    """The default field list asks for velocity components and mixed-layer
    depth, which the synthetic simulation does not write, and the step
    computes a climatology of the rest rather than failing."""
    filename = find_climatology_file(climatology, 'ANN')
    with xr.open_dataset(filename) as ds:
        assert 'Temperature' in ds
        assert 'PseudoThickness' in ds
        assert 'velocityZonal' not in ds
        assert 'mixedLayerDepth' not in ds


@pytest.fixture(scope='module')
def climatology(tmp_path_factory):
    """Run the climatology step on a synthetic data set, once."""
    work_dir = tmp_path_factory.mktemp('climatology')
    filenames = _write_monthly_means(str(work_dir))

    config = PolarisConfigParser()
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')

    component = Ocean()
    # the analysis reads Omega output only; a step that never runs a model
    # does not go through set_model()
    component.model = 'omega'

    step = Climatology(
        component=component,
        subdir='analysis/climatology/0001-0003',
        start_year=START_YEAR,
        end_year=END_YEAR,
    )
    step.work_dir = str(work_dir)
    step.config = config
    step.logger = logging.getLogger(__name__)
    step.input_filenames = filenames
    step.run()

    return str(work_dir)


def _write_monthly_means(work_dir):
    """Write one file per month with Omega names and CF time metadata"""
    filenames = []
    day = 0.0
    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            first, last = day, day + DAYS_IN_MONTH[month - 1]
            day = last
            filename = f'ocn.hist.{year:04d}-{month:02d}.nc'
            _write_month(
                f'{work_dir}/{filename}',
                monthly_mean(year, month),
                first,
                last,
            )
            filenames.append(filename)
    return filenames


def _write_month(filename, value, first_day, last_day):
    """Write one month of synthetic monthly means"""
    cells = np.arange(N_CELLS)[:, None]
    levels = np.arange(N_LEVELS)[None, :]
    field = value + cells + 100.0 * levels
    ds = xr.Dataset(
        data_vars=dict(
            Temperature=(
                ('time', 'NCells', 'NVertLayers'),
                field[None, :, :],
            ),
            Salinity=(('time', 'NCells', 'NVertLayers'), field[None, :, :]),
            SshCell=(('time', 'NCells'), value + cells.T),
            PseudoThickness=(
                ('time', 'NCells', 'NVertLayers'),
                np.full((1, N_CELLS, N_LEVELS), 10.0),
            ),
            GeomZMid=(('time', 'NCells', 'NVertLayers'), field[None, :, :]),
            GeomZInterface=(
                ('time', 'NCells', 'NVertLayersP1'),
                np.zeros((1, N_CELLS, N_LEVELS + 1)),
            ),
            time_bnds=(('time', 'd2'), [[first_day, last_day]]),
        ),
        coords=dict(time=('time', [0.5 * (first_day + last_day)])),
    )
    ds.time.attrs = dict(
        units='days since 0001-01-01',
        calendar='noleap',
        bounds='time_bnds',
    )
    ds.to_netcdf(filename, unlimited_dims=['time'])


def _day_weighted(months):
    """The day-weighted mean of the monthly climatologies of some months"""
    weights = [float(DAYS_IN_MONTH[month - 1]) for month in months]
    values = [
        np.mean(
            [
                monthly_mean(year, month)
                for year in range(START_YEAR, END_YEAR + 1)
            ]
        )
        for month in months
    ]
    return float(np.average(values, weights=weights))


def _assert_field(work_dir, season, expected):
    """The synthetic field is ``expected`` plus a known per-cell, per-level
    offset, so one comparison covers the whole array"""
    filename = find_climatology_file(work_dir, season)
    with xr.open_dataset(filename) as ds:
        cells = np.arange(N_CELLS)[:, None]
        levels = np.arange(N_LEVELS)[None, :]
        offsets = cells + 100.0 * levels
        field = ds.Temperature.isel(time=0).values
        np.testing.assert_allclose(field, expected + offsets)
