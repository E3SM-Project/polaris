"""
Unit tests for the accumulator that inherits months from earlier analyses.

Inheritance is the piece of the analysis whose failure modes are silent: a
stamp that matches when it should not inherits numbers computed by different
code, from a different simulation, or under different options, and nothing
reports it.  So most of what is tested here is *not* inheriting -- the cases
in which a cache is on disk, is readable, holds the months that were asked
for, and must be ignored anyway.

The kernel is a stub that records the months it was asked for, since what is
under test is the bookkeeping around it rather than any reduction.
"""

import logging
import os

import pytest
import xarray as xr

from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis.accumulate import (
    COMPLETION_MARKER,
    Accumulator,
    read_stamp,
)
from polaris.tasks.ocean.analysis.sim_files import SimFile, year_range_key

CACHE = 'counter_cache.nc'


def test_a_first_run_computes_every_month(product_dir):
    step = _run(product_dir, 1, 2)
    assert step.computed == _months(1, 2)


def test_an_overlapping_range_inherits_the_months_it_shares(product_dir):
    first = _run(product_dir, 1, 2)
    second = _run(product_dir, 2, 3)
    assert first.computed == _months(1, 2)
    # the twelve months of year 2 come from the first run's cache
    assert second.computed == _months(3, 3)


def test_an_inherited_cache_is_declared_as_an_input(product_dir):
    _run(product_dir, 1, 2)
    step = _setup(product_dir, 2, 3)
    targets = [entry['target'] for entry in step.input_data]
    assert os.path.join(_step_dir(product_dir, 1, 2), CACHE) in targets


def test_a_range_inside_an_earlier_one_computes_nothing(product_dir):
    _run(product_dir, 1, 3)
    step = _run(product_dir, 2, 2)
    assert step.computed == []


def test_the_series_is_every_month_of_the_range_in_order(product_dir):
    _run(product_dir, 1, 2)
    step = _run(product_dir, 2, 3)
    ds = step.finalized
    dates = list(zip(ds.year.values, ds.month.values, strict=True))
    assert [(int(year), int(month)) for year, month in dates] == _months(2, 3)
    # the value each month reduces to says which month it came from, so an
    # inherited month landing in the wrong slot would show up here
    assert [int(value) for value in ds.value.values] == [
        100 * year + month for year, month in _months(2, 3)
    ]


def test_the_months_inherited_are_reported(product_dir, caplog):
    _run(product_dir, 1, 2)
    with caplog.at_level(logging.INFO):
        _run(product_dir, 2, 3)
    assert 'inheriting 12 months, computing 12' in caplog.text
    assert 'inheriting from' in caplog.text


def test_a_step_that_did_not_finish_is_not_inherited_from(product_dir):
    _run(product_dir, 1, 2, complete=False)
    step = _run(product_dir, 2, 3)
    assert step.computed == _months(2, 3)


def test_the_reason_a_candidate_was_turned_down_is_reported(
    product_dir, caplog
):
    _run(product_dir, 1, 2, complete=False)
    with caplog.at_level(logging.INFO):
        _run(product_dir, 2, 3)
    assert 'not inheriting from' in caplog.text
    assert 'did not finish' in caplog.text


def test_a_cache_from_another_simulation_is_not_inherited_from(product_dir):
    _run(product_dir, 1, 2, simulation='/other/omega.yml')
    step = _run(product_dir, 2, 3)
    assert step.computed == _months(2, 3)


def test_a_cache_computed_under_other_options_is_not_inherited_from(
    product_dir,
):
    _run(
        product_dir, 1, 2, product_stamp={'elevation_ranges': 'top_to_bottom'}
    )
    step = _run(
        product_dir, 2, 3, product_stamp={'elevation_ranges': 'top_to_-700m'}
    )
    assert step.computed == _months(2, 3)


def test_a_cache_from_an_older_kernel_is_not_inherited_from(product_dir):
    _run(product_dir, 1, 2, kernel_version=1)
    step = _run(product_dir, 2, 3, kernel_version=2)
    assert step.computed == _months(2, 3)


def test_a_cache_from_another_product_is_not_inherited_from(product_dir):
    """Two products would have to share a directory for this to arise, but a
    cache is admitted on its content and the content says which kernel wrote
    it."""
    _run(product_dir, 1, 2)
    step = _setup(product_dir, 2, 3)
    step.stamp['kernel'] = 'SomeOtherAccumulator'
    _link_inputs(step)
    step.run()
    assert step.computed == _months(2, 3)


def test_nothing_outside_the_product_directory_is_consulted(product_dir):
    """A cache under a sibling of the *product* rather than of the step is
    not a candidate, whatever its stamp says."""
    _run(product_dir, 1, 2)
    other_product = os.path.join(os.path.dirname(product_dir), 'other_product')
    os.rename(product_dir, other_product)
    os.makedirs(product_dir)
    step = _run(product_dir, 1, 2)
    assert step.computed == _months(1, 2)


def test_a_directory_that_is_not_a_range_is_not_a_candidate(product_dir):
    """The scope is sibling *range* directories; a cache filed anywhere else
    under the product was not written by this step class."""
    _run(product_dir, 1, 2)
    os.rename(
        _step_dir(product_dir, 1, 2), os.path.join(product_dir, 'scratch')
    )
    step = _run(product_dir, 1, 2)
    assert step.computed == _months(1, 2)


def test_reuse_can_be_turned_off(product_dir):
    _run(product_dir, 1, 2)
    step = _run(product_dir, 2, 3, reuse_previous=False)
    assert step.computed == _months(2, 3)


def test_the_step_own_partial_cache_is_what_a_retry_starts_from(product_dir):
    """An interrupted run leaves a cache in its own directory, which is not
    complete and so is not a seed, but is still where its retry picks up."""
    interrupted = _setup(product_dir, 1, 2)
    interrupted.stop_after = 6
    _link_inputs(interrupted)
    with pytest.raises(_Interrupted):
        interrupted.run()

    retry = _run(product_dir, 1, 2)
    assert retry.computed == _months(1, 2)[6:]


def test_a_stale_cache_in_the_step_own_directory_is_ignored(product_dir):
    """Re-running the same range after changing an option that governs the
    product lands on the same directory, so its own cache has to be admitted
    on its stamp like any other."""
    _run(product_dir, 1, 2, product_stamp={'ranges': 'a'}, complete=False)
    step = _run(product_dir, 1, 2, product_stamp={'ranges': 'b'})
    assert step.computed == _months(1, 2)


def test_the_cache_carries_the_stamp_it_was_computed_under(product_dir):
    step = _run(product_dir, 1, 1, product_stamp={'ranges': 'a'})
    stamp = read_stamp(os.path.join(step.work_dir, CACHE))
    assert stamp == step.stamp
    assert stamp['ranges'] == 'a'
    assert stamp['kernel_version'] == '1'


def test_the_cache_is_the_declared_output(product_dir):
    step = _run(product_dir, 1, 1)
    # every analysis step also declares the manifest fragment the base class
    # writes for the publish step
    assert step.outputs == [FRAGMENT_FILENAME, CACHE]
    assert os.path.exists(os.path.join(step.work_dir, CACHE))


class _Interrupted(Exception):
    """What a run that is stopped part way through raises"""


class _Counter(Accumulator):
    """An accumulator whose kernel records the months it was asked for"""

    def __init__(
        self,
        component,
        subdir,
        start_year,
        end_year,
        kernel_version,
        product_stamp,
    ):
        super().__init__(
            component=component,
            name='counter',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            cache_filename=CACHE,
            kernel_version=kernel_version,
            ntasks=1,
            cpus_per_task=1,
        )
        self.computed: list = []
        self.finalized = None
        self.stop_after = None
        self._product_stamp = dict(product_stamp)

    def product_stamp(self):
        return dict(self._product_stamp)

    def compute_month(self, filename, year, month):
        if self.stop_after is not None and len(self.computed) >= (
            self.stop_after
        ):
            raise _Interrupted(f'stopped before {year:04d}-{month:02d}')
        self.computed.append((year, month))
        return xr.Dataset(dict(value=xr.DataArray(100.0 * year + month)))

    def finalize(self, ds):
        self.finalized = ds


class _FakeOmegaConfig:
    def __init__(self, filename):
        self.filename = filename


class _FakeSimulationFiles:
    """What the simulation would look like, without one being on disk"""

    def __init__(self, simulation, simulation_path):
        self.omega_config = _FakeOmegaConfig(simulation)
        self.simulation_path = simulation_path
        self.simulation_name = 'sim'

    def monthly_mean_files(self, start_year, end_year):
        return [
            SimFile(
                path=os.path.join(
                    self.simulation_path, f'hist.{year:04d}-{month:02d}.nc'
                ),
                year=year,
                month=month,
            )
            for year, month in _months(start_year, end_year)
        ]


@pytest.fixture
def product_dir(tmp_path):
    """The product's directory, the only place seeds are looked for"""
    path = tmp_path / 'work' / 'analysis' / 'counter'
    path.mkdir(parents=True)
    return str(path)


def _months(start_year, end_year):
    return [
        (year, month)
        for year in range(start_year, end_year + 1)
        for month in range(1, 13)
    ]


def _step_dir(product_dir, start_year, end_year):
    return os.path.join(product_dir, year_range_key(start_year, end_year))


def _setup(
    product_dir,
    start_year,
    end_year,
    kernel_version=1,
    product_stamp=None,
    simulation='/sim/omega.yml',
    reuse_previous=True,
):
    """
    A step at its range-keyed directory, set up as ``polaris setup`` would
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean', 'model', 'omega')
    config.set(
        'ocean_analysis',
        'reuse_previous',
        'True' if reuse_previous else 'False',
        user=True,
    )

    component = Ocean()
    component.model = 'omega'
    key = year_range_key(start_year, end_year)
    step = _Counter(
        component=component,
        subdir=f'analysis/counter/{key}',
        start_year=start_year,
        end_year=end_year,
        kernel_version=kernel_version,
        product_stamp=product_stamp or {},
    )
    work_dir = _step_dir(product_dir, start_year, end_year)
    os.makedirs(work_dir, exist_ok=True)
    step.work_dir = work_dir
    step.config = config
    step.logger = logging.getLogger('accumulate')
    step.get_sim_files = lambda: _FakeSimulationFiles(  # type: ignore[method-assign]
        simulation=simulation, simulation_path=os.path.dirname(simulation)
    )
    step.setup()
    return step


def _link_inputs(step):
    """
    Symlink the inputs the step declared, which ``polaris setup`` does after
    ``setup()`` returns

    Only the inherited caches are on disk here; the monthly means are never
    read, since the kernel is a stub.
    """
    for entry in step.input_data:
        target = entry['target']
        if target is None or not os.path.exists(target):
            continue
        link = os.path.join(step.work_dir, entry['filename'])
        if not os.path.exists(link):
            os.symlink(target, link)


def _run(product_dir, start_year, end_year, complete=True, **kwargs):
    """Set up a step, run it, and mark it complete the way Polaris does"""
    step = _setup(product_dir, start_year, end_year, **kwargs)
    _link_inputs(step)
    step.runtime_setup()
    step.run()
    if complete:
        marker = os.path.join(step.work_dir, COMPLETION_MARKER)
        with open(marker, 'w') as log_file:
            log_file.write('step completed\n')
    return step
