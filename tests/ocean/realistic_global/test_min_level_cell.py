import configparser
import importlib.resources as imp_res
import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.forward import (
    TIME_INTEGRATORS,
    DatabaseInitialCondition,
)
from polaris.tasks.ocean.realistic_global.min_level_cell import (
    TopLevelInitialCondition,
    add_top_level,
    compare_shifted,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    INIT_FILENAME,
    MESH_FILENAME,
)

PACKAGE = 'polaris.tasks.ocean.realistic_global.min_level_cell'


def _task(time_integrator='split_explicit', model='mpas-ocean'):
    """A registered min_level_cell task, with its config combined"""
    component = Ocean()
    add_realistic_global_tasks(component=component)
    subdir = (
        f'spherical/realistic_global/e3sm-qu240/min_level_cell/'
        f'{time_integrator}'
    )
    task = component.tasks[subdir]
    config = task.config
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.set('ocean', 'model', model)
    config.combine()
    return task


def _column_dataset():
    """
    A small MPAS-Ocean dataset: three cells, the last of them land, and two
    edges, on a four-level grid
    """
    rng = np.random.default_rng(0)
    n_cells, n_edges, n_levels = 3, 2, 4
    ds = xr.Dataset()
    ds['maxLevelCell'] = ('nCells', np.array([4, 2, 0], dtype=np.int32))
    ds['maxLevelCell'].attrs['units'] = 'unitless'
    ds['bottomDepth'] = ('nCells', np.array([400.0, 200.0, 0.0]))
    ds['refBottomDepth'] = ('nVertLevels', 100.0 * np.arange(1, 5))
    ds['refInterfaces'] = ('nVertLevelsP1', 100.0 * np.arange(5))
    ds['temperature'] = (
        ('Time', 'nCells', 'nVertLevels'),
        rng.random((1, n_cells, n_levels)),
    )
    ds['normalVelocity'] = (
        ('Time', 'nEdges', 'nVertLevels'),
        rng.random((1, n_edges, n_levels)),
    )
    ds['edgeMask'] = (
        ('nEdges', 'nVertLevels'),
        np.ones((n_edges, n_levels), dtype=np.int32),
    )
    return ds


def _output_dataset():
    """A small history file, as a run without the added level writes it"""
    rng = np.random.default_rng(1)
    n_time, n_cells, n_levels = 3, 4, 5
    ds = xr.Dataset()
    ds['xtime'] = (
        'Time',
        np.array(
            [f'0001-01-01_{hour:02d}:00:00' for hour in range(n_time)],
            dtype='S64',
        ),
    )
    ds['temperature'] = (
        ('Time', 'nCells', 'nVertLevels'),
        rng.random((n_time, n_cells, n_levels)),
    )
    ds['ssh'] = (('Time', 'nCells'), rng.random((n_time, n_cells)))
    return ds


def _shifted_output(ds):
    """
    The same history with an inactive level added, holding the fill value
    MPAS-Ocean writes there, as a correct run with the added level writes it
    """
    shifted = add_top_level(ds)
    temperature = shifted.temperature.values.copy()
    temperature[:, :, 0] = -1.0e34
    shifted['temperature'] = (shifted.temperature.dims, temperature)
    return shifted


@pytest.mark.parametrize('time_integrator', TIME_INTEGRATORS)
def test_task_runs_the_cached_qu240_with_and_without_the_added_level(
    time_integrator,
):
    task = _task(time_integrator)
    assert list(task.steps) == [
        'reference',
        'add_top_level',
        'shifted',
        'compare',
    ]
    reference = task.steps['reference']
    add_top_level_step = task.steps['add_top_level']
    shifted = task.steps['shifted']

    # the two runs differ only in where their input files come from
    assert isinstance(reference.init_condition, DatabaseInitialCondition)
    assert isinstance(shifted.init_condition, TopLevelInitialCondition)
    assert shifted.init_condition.add_top_level is add_top_level_step
    assert shifted.init_condition.source is reference.init_condition
    assert add_top_level_step.init_condition is reference.init_condition
    assert reference.config is shifted.config


def test_task_config_overrides_the_mesh_config():
    """
    e3sm-qu240's own config sets a run duration, so the task's has to come
    after it to take effect
    """
    task = _task()
    task_cfg = configparser.ConfigParser()
    with imp_res.as_file(
        imp_res.files(PACKAGE).joinpath('min_level_cell.cfg')
    ) as path:
        task_cfg.read(path)
    section = 'realistic_global_forward'
    for option in task_cfg[section]:
        assert task.config.get(section, option) == task_cfg[section][option]


def test_rk4_variant_runs_rk4():
    """The rk4 variant has to read rk4.cfg, or it repeats the default run"""
    rk4_cfg = configparser.ConfigParser()
    with imp_res.as_file(
        imp_res.files('polaris.tasks.ocean.realistic_global.forward').joinpath(
            'rk4.cfg'
        )
    ) as path:
        rk4_cfg.read(path)
    section = 'realistic_global_forward'
    config = _task('rk4').config
    for option in rk4_cfg[section]:
        assert config.get(section, option) == rk4_cfg[section][option]


@pytest.mark.parametrize(
    'model, skipped', [('mpas-ocean', False), ('omega', True)]
)
def test_task_is_skipped_for_omega(model, skipped):
    task = _task(model=model)
    task.configure()
    assert (task.skip_reason is not None) == skipped


def test_shifted_run_reads_the_files_with_the_added_level():
    task = _task()
    add_top_level_step = task.steps['add_top_level']
    shifted = task.steps['shifted']
    path = add_top_level_step.path

    shifted.init_condition.add_input_files(shifted)
    targets = {
        entry['filename']: entry['work_dir_target']
        for entry in shifted.input_data
    }
    assert targets['<<<horiz_mesh>>>'] == f'{path}/{MESH_FILENAME}'
    assert targets['<<<init>>>'] == f'{path}/{INIT_FILENAME}'
    # the cached initial condition carries the wind stress, so there is no
    # forcing file of its own to pass on
    assert '<<<forcing>>>' not in targets
    assert shifted.graph_target == f'{path}/graph.info'


def test_add_top_level_step_reads_the_cached_files_and_graph():
    step = _task().steps['add_top_level']
    step.setup()
    filenames = [entry['filename'] for entry in step.input_data]
    assert '<<<horiz_mesh>>>' in filenames
    assert '<<<init>>>' in filenames
    # the shifted run's graph comes through this step
    assert 'graph.info' in filenames


def test_add_top_level_moves_every_level_down_by_one():
    ds = _column_dataset()
    shifted = add_top_level(ds)

    assert shifted.sizes['nVertLevels'] == ds.sizes['nVertLevels'] + 1
    assert shifted.sizes['nVertLevelsP1'] == ds.sizes['nVertLevelsP1'] + 1
    for var in ['refBottomDepth', 'refInterfaces', 'temperature', 'edgeMask']:
        da = shifted[var]
        dim = 'nVertLevelsP1' if 'nVertLevelsP1' in da.dims else 'nVertLevels'
        np.testing.assert_array_equal(
            da.isel({dim: slice(1, None)}).values, ds[var].values
        )
        assert np.all(da.isel({dim: 0}).values == 0)
        assert da.dtype == ds[var].dtype

    # a zero-thickness reference level at the surface leaves the active
    # levels at their reference depths
    assert shifted.refInterfaces.values[0] == shifted.refInterfaces.values[1]

    # the land cell stays without an active level
    np.testing.assert_array_equal(shifted.maxLevelCell.values, [5, 3, 0])
    np.testing.assert_array_equal(shifted.minLevelCell.values, [2, 2, 2])
    assert shifted.maxLevelCell.dtype == ds.maxLevelCell.dtype
    assert shifted.maxLevelCell.attrs == ds.maxLevelCell.attrs

    xr.testing.assert_identical(shifted.bottomDepth, ds.bottomDepth)


def test_add_top_level_moves_an_existing_min_level_cell_down():
    ds = _column_dataset()
    ds['minLevelCell'] = ('nCells', np.array([1, 2, 1], dtype=np.int32))
    shifted = add_top_level(ds)
    np.testing.assert_array_equal(shifted.minLevelCell.values, [2, 3, 2])


def test_add_top_level_step_writes_one_file_for_a_shared_source(
    tmp_path, monkeypatch
):
    """
    A cached initial condition gives the mesh and the initial state in one
    file, which is shifted once and written once
    """
    step = _task().steps['add_top_level']
    step.logger = logging.getLogger(__name__)
    monkeypatch.chdir(tmp_path)
    _column_dataset().to_netcdf('source.nc')
    os.symlink('source.nc', step.get_horiz_mesh_filename())
    os.symlink('source.nc', step.get_init_filename())

    step.run()

    assert not os.path.islink(MESH_FILENAME)
    assert os.path.realpath(INIT_FILENAME) == os.path.realpath(MESH_FILENAME)
    with xr.open_dataset(INIT_FILENAME) as ds:
        np.testing.assert_array_equal(ds.minLevelCell.values, [2, 2, 2])


def test_compare_shifted_passes_identical_runs(caplog):
    ds = _output_dataset()
    logger = logging.getLogger(__name__)
    with caplog.at_level(logging.INFO):
        assert compare_shifted(ds, _shifted_output(ds), logger)
    assert 'temperature PASS' in caplog.text
    assert 'xtime PASS' in caplog.text


def test_compare_shifted_reports_where_runs_differ(caplog):
    ds = _output_dataset()
    shifted = _shifted_output(ds)
    temperature = shifted.temperature.values.copy()
    temperature[1, 2, 3] += 1.0e-15
    shifted['temperature'] = (shifted.temperature.dims, temperature)
    logger = logging.getLogger(__name__)
    with caplog.at_level(logging.INFO):
        assert not compare_shifted(ds, shifted, logger)
    assert '1 of' in caplog.text
    assert 'first at time index 1' in caplog.text
    assert 'ssh PASS' in caplog.text


@pytest.mark.parametrize('both', [True, False])
def test_compare_shifted_counts_a_nan_in_one_run_only(both):
    ds = _output_dataset()
    shifted = _shifted_output(ds)
    ssh = shifted.ssh.values.copy()
    ssh[2, 1] = np.nan
    shifted['ssh'] = (shifted.ssh.dims, ssh)
    if both:
        ds['ssh'] = (ds.ssh.dims, ssh.copy())
    logger = logging.getLogger(__name__)
    assert compare_shifted(ds, shifted, logger) == both


def test_compare_shifted_needs_the_added_level(caplog):
    """
    Comparing a run with itself would pass without testing anything, so a
    run without the added level fails
    """
    ds = _output_dataset()
    logger = logging.getLogger(__name__)
    assert not compare_shifted(ds, ds, logger)
    assert 'one more than the reference run' in caplog.text
