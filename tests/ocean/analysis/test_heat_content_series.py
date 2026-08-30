"""
Unit tests for the ocean heat content time series step.

The kernel itself is tested in ``tests/ocean/test_heat_content.py``; what is
tested here is the step around it: that the global integral is the
mass-weighted one, that a land column drops out of it rather than poisoning
it with a ``NaN``, that a range the vertical machinery cannot reach yet is
left out and said so, and that what the step publishes is what it declared.

Everything is synthetic and small, but it is read through the same
``open_model_dataset`` path as real Omega output, with Omega's names and
dimensions, so a change in the name mapping would show up here.
"""

import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.model.layer_mass import RhoSw
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis.heat_content_config import get_specific_heat
from polaris.tasks.ocean.analysis.heat_content_series import (
    PLOT_FILENAME,
    SERIES_FILENAME,
    HeatContentSeries,
    series_variable,
)
from polaris.tasks.ocean.analysis.sim_files import SimFile, year_range_key

N_CELLS = 4
N_LEVELS = 3

# a uniform pseudo-thickness, so that the mass of a column is a number that
# can be written down
THICKNESS = 50.0

AREA_CELL = np.array([1.0e6, 2.0e6, 3.0e6, 4.0e6])

# the last column is land: its bottommost valid layer is above its topmost,
# which is how a column with no ocean in it is spelled
LAND_CELL = N_CELLS - 1

WHOLE_COLUMN = series_variable('top_to_bottom')


def test_the_series_is_the_mass_weighted_global_integral(step):
    step.run()
    with xr.open_dataset(os.path.join(step.work_dir, SERIES_FILENAME)) as ds:
        series = ds[WHOLE_COLUMN].values
        months = ds.month.values
    expected = [_expected(step.config, month) for month in months]
    np.testing.assert_allclose(series, expected, rtol=1e-12)


def test_a_land_column_contributes_nothing_rather_than_a_nan(step):
    """A NaN here would poison the global sum, so the masked column has to
    drop out of it."""
    step.run()
    with xr.open_dataset(os.path.join(step.work_dir, SERIES_FILENAME)) as ds:
        series = ds[WHOLE_COLUMN].values
    # the kernel masks a column with no mass in the range, so a global sum
    # that did not skip the mask would be NaN for every month
    assert np.all(np.isfinite(series))
    assert series[0] > 0.0


def test_the_series_covers_the_range_in_order(step):
    step.run()
    with xr.open_dataset(os.path.join(step.work_dir, SERIES_FILENAME)) as ds:
        dates = list(zip(ds.year.values, ds.month.values, strict=True))
        years = ds.simulationYear.values
    assert [(int(year), int(month)) for year, month in dates] == [
        (1, month) for month in range(1, 13)
    ]
    assert np.all(np.diff(years) > 0.0)


def test_the_product_and_its_plot_are_the_declared_outputs(step):
    # runtime_setup writes the manifest fragment the base class declares, so
    # a step run without it is missing one of its own outputs
    step.runtime_setup()
    step.run()
    assert SERIES_FILENAME in step.outputs
    assert PLOT_FILENAME in step.outputs
    for output in step.outputs:
        assert os.path.exists(os.path.join(step.work_dir, output)), output


def test_the_series_says_what_it_was_computed_from(step):
    step.run()
    with xr.open_dataset(os.path.join(step.work_dir, SERIES_FILENAME)) as ds:
        attrs = ds.attrs
        units = ds[WHOLE_COLUMN].attrs['units']
    assert units == 'J'
    assert attrs['year_range'] == year_range_key(1, 1)
    assert attrs['provenance_elevation_ranges'] == 'top_to_bottom'
    assert attrs['provenance_kernel_version'] == '1'


def test_a_range_that_is_not_implemented_yet_is_left_out(tmp_path, caplog):
    step = _make_step(tmp_path, ranges='top:-700.0, top:bottom')
    with caplog.at_level(logging.INFO):
        step.run()
    assert 'top_to_-700m' in caplog.text
    assert 'not implemented yet' in caplog.text
    with xr.open_dataset(os.path.join(step.work_dir, SERIES_FILENAME)) as ds:
        assert WHOLE_COLUMN in ds
        assert series_variable('top_to_-700m') not in ds


def test_the_stamp_names_the_ranges_that_were_computed(tmp_path):
    """A cache holding the whole column alone must not be inherited by a run
    that can integrate every range, so the stamp says what was computed and
    not what was asked for."""
    step = _make_step(tmp_path, ranges='top:-700.0, -700.0:bottom, top:bottom')
    assert step.stamp['elevation_ranges'] == 'top_to_bottom'


def test_a_configuration_with_no_computable_range_is_reported_at_setup(
    tmp_path,
):
    with pytest.raises(ValueError, match='top:bottom'):
        _make_step(tmp_path, ranges='top:-700.0')


def test_a_month_the_integral_cannot_be_taken_from_is_an_error(tmp_path):
    step = _make_step(tmp_path, with_temperature=False)
    with pytest.raises(ValueError, match='temperature'):
        step.run()


@pytest.fixture
def step(tmp_path):
    return _make_step(tmp_path)


class _FakeOmegaConfig:
    def __init__(self, filename):
        self.filename = filename


class _FakeSimulationFiles:
    """The simulation's files, without an Omega configuration to read"""

    def __init__(self, simulation_path):
        self.simulation_path = simulation_path
        self.omega_config = _FakeOmegaConfig(
            os.path.join(simulation_path, 'omega.yml')
        )
        self.simulation_name = 'sim'

    def mesh_filename(self):
        return os.path.join(self.simulation_path, 'mesh.nc')

    def vert_coord_filename(self):
        return os.path.join(self.simulation_path, 'vert_coord.nc')

    def monthly_mean_files(self, start_year, end_year):
        return [
            SimFile(
                path=os.path.join(
                    self.simulation_path, f'hist.{year:04d}-{month:02d}.nc'
                ),
                year=year,
                month=month,
            )
            for year in range(start_year, end_year + 1)
            for month in range(1, 13)
        ]


def _temperature(month):
    """A temperature that says which month, cell and level it came from"""
    cells = np.arange(N_CELLS)[:, None]
    levels = np.arange(N_LEVELS)[None, :]
    return float(month) + 0.5 * levels + 0.25 * cells


def _expected(config, month):
    """
    The mass-weighted global integral, written out here rather than taken
    from the code under test

    The land column is left out, since a column with no valid layer has no
    heat content to contribute rather than a heat content of zero.
    """
    specific_heat = get_specific_heat(config)
    column = _temperature(month).sum(axis=1) * RhoSw * THICKNESS
    ocean = [cell for cell in range(N_CELLS) if cell != LAND_CELL]
    return specific_heat * float(
        sum(AREA_CELL[cell] * column[cell] for cell in ocean)
    )


def _write_simulation(sim_path, start_year, end_year, with_temperature):
    """The mesh, the vertical coordinate and the monthly means, Omega-style"""
    xr.Dataset(
        dict(
            AreaCell=('NCells', AREA_CELL),
            LatCell=('NCells', np.linspace(-1.0, 1.0, N_CELLS)),
            LonCell=('NCells', np.linspace(0.0, 6.0, N_CELLS)),
        )
    ).to_netcdf(os.path.join(sim_path, 'mesh.nc'))

    max_level = np.full(N_CELLS, N_LEVELS, dtype=np.int32)
    max_level[LAND_CELL] = 0
    xr.Dataset(
        dict(
            MinLayerCell=('NCells', np.ones(N_CELLS, dtype=np.int32)),
            MaxLayerCell=('NCells', max_level),
        )
    ).to_netcdf(os.path.join(sim_path, 'vert_coord.nc'))

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            data = dict(
                PseudoThickness=(
                    ('time', 'NCells', 'NVertLayers'),
                    np.full((1, N_CELLS, N_LEVELS), THICKNESS),
                ),
            )
            if with_temperature:
                data['Temperature'] = (
                    ('time', 'NCells', 'NVertLayers'),
                    _temperature(month)[None, :, :],
                )
            filename = f'hist.{year:04d}-{month:02d}.nc'
            xr.Dataset(data).to_netcdf(os.path.join(sim_path, filename))


def _make_step(
    tmp_path,
    ranges='top:bottom',
    start_year=1,
    end_year=1,
    with_temperature=True,
):
    """A step with a synthetic simulation to read, set up as Polaris would"""
    sim_path = tmp_path / 'sim'
    sim_path.mkdir()
    _write_simulation(str(sim_path), start_year, end_year, with_temperature)

    key = year_range_key(start_year, end_year)
    work_dir = tmp_path / 'work' / 'analysis' / 'heat_content_series' / key
    work_dir.mkdir(parents=True)

    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean', 'model', 'omega')
    config.set('ocean_analysis_ohc', 'elevation_ranges', ranges, user=True)

    component = Ocean()
    component.model = 'omega'
    step = HeatContentSeries(
        component=component,
        subdir=f'analysis/heat_content_series/{key}',
        start_year=start_year,
        end_year=end_year,
    )
    step.work_dir = str(work_dir)
    step.config = config
    step.logger = logging.getLogger('heat_content_series')
    step.get_sim_files = lambda: _FakeSimulationFiles(  # type: ignore[method-assign]
        str(sim_path)
    )
    step.setup()
    for entry in step.input_data:
        os.symlink(
            entry['target'], os.path.join(str(work_dir), entry['filename'])
        )
    return step
