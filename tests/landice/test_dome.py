import logging
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.config import PolarisConfigParser
from polaris.landice.mesh import make_mali_mesh
from polaris.landice.model import MaliModelStep
from polaris.tasks.landice import Landice
from polaris.tasks.landice.add_tasks import add_landice_tasks
from polaris.tasks.landice.dome.init import _add_dome_initial_condition
from polaris.tasks.landice.dome.validate import EXACT_NORMS, FO_NORMS

TASKS = [
    f'dome/2km/{solver}/{task}'
    for solver in ['sia', 'fo']
    for task in ['smoke_test', 'decomp', 'restart']
]


def test_dome_tasks():
    component = Landice()
    add_landice_tasks(component)

    dome_tasks = [path for path in component.tasks if path.startswith('dome/')]
    assert sorted(dome_tasks) == sorted(TASKS)
    # the mesh and initial condition are shared by all the tasks
    assert 'dome/2km/init' in component.steps


@pytest.mark.parametrize('solver', ['sia', 'fo'])
def test_dome_steps_need_albany_for_first_order(solver):
    component = Landice()
    add_landice_tasks(component)

    for task in ['smoke_test', 'decomp', 'restart']:
        path = f'dome/2km/{solver}/{task}'
        for step in component.tasks[path].steps.values():
            if isinstance(step, MaliModelStep):
                assert step.needs_albany == (solver == 'fo')


def test_dome_restart_reads_full_run_restart():
    component = Landice()
    add_landice_tasks(component)

    task = component.tasks['dome/2km/sia/restart']
    full = task.steps['full_run']
    restart = task.steps['restart_run']
    inputs = {entry['filename']: entry for entry in restart.input_data}

    assert 'rst.0001.nc' in full.outputs
    assert inputs['rst.0001.nc']['work_dir_target'] == (
        f'{full.path}/rst.0001.nc'
    )


@pytest.mark.parametrize('solver', ['sia', 'fo'])
@pytest.mark.parametrize('gpus_per_node', [None, 0, 4])
def test_dome_restart_norms_on_gpus(solver, gpus_per_node):
    component = Landice()
    add_landice_tasks(component)
    if gpus_per_node is not None:
        component.parallel_system = SimpleNamespace(
            gpus_per_node=gpus_per_node
        )

    validate = component.tasks[f'dome/2km/{solver}/restart'].steps['validate']

    # only the first-order solver on GPUs is not bit-for-bit
    expected = FO_NORMS if solver == 'fo' and gpus_per_node else EXACT_NORMS
    assert validate._get_norms() is expected


def test_make_mali_mesh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logger = logging.getLogger(__name__)
    ds_mesh = make_planar_hex_mesh(
        nx=6, ny=8, dc=2000.0, nonperiodic_x=True, nonperiodic_y=True
    )
    ds_mesh = convert(cull(ds_mesh, logger=logger), logger=logger)
    write_netcdf(ds_mesh, 'culled_mesh.nc')

    make_mali_mesh(
        in_filename='culled_mesh.nc',
        out_filename='mali_mesh.nc',
        levels=5,
        logger=logger,
        graph_filename='graph.info',
    )

    with xr.open_dataset('mali_mesh.nc') as ds:
        assert ds.sizes['nVertLevels'] == 5
        assert ds.sizes['nCells'] == ds_mesh.sizes['nCells']
        for variable in ['thickness', 'bedTopography', 'sfcMassBal']:
            assert variable in ds
    with open('graph.info') as f:
        n_cells = int(f.readline().split()[0])
    assert n_cells == ds_mesh.sizes['nCells']


@pytest.mark.parametrize('dome_type', ['halfar', 'cism'])
def test_dome_initial_condition(dome_type):
    ds = _make_mali_dataset(nx=30, ny=34, dc=2000.0, levels=10)
    config = _make_dome_config(dome_type)

    _add_dome_initial_condition(ds, config)

    thickness = ds.thickness.isel(Time=0).values
    center_cell = np.argmax(thickness)
    # the dome is centered on a cell at the origin
    assert ds.xCell.values[center_cell] == 0.0
    assert ds.yCell.values[center_cell] == 0.0
    np.testing.assert_allclose(thickness.max(), 2000.0 * np.sqrt(0.125))
    r = np.sqrt(ds.xCell.values**2 + ds.yCell.values**2)
    assert np.all(thickness[r >= 60000.0 * np.sqrt(0.125)] == 0.0)
    assert np.all(ds.bedTopography.values == 0.0)
    np.testing.assert_allclose(ds.layerThicknessFractions.values, 0.1)
    assert np.all(ds.sfcMassBal.values == 0.0)


def test_dome_initial_condition_unknown_type():
    ds = _make_mali_dataset(nx=6, ny=8, dc=2000.0, levels=2)
    config = _make_dome_config('unknown')

    with pytest.raises(ValueError, match='dome_type'):
        _add_dome_initial_condition(ds, config)


def _make_mali_dataset(nx, ny, dc, levels):
    """The mesh coordinates and the fields the dome sets, without MALI"""
    ds_mesh = make_planar_hex_mesh(
        nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=True
    )
    n_cells = ds_mesh.sizes['nCells']
    ds = ds_mesh[
        ['xCell', 'yCell', 'xEdge', 'yEdge', 'xVertex', 'yVertex']
    ].copy(deep=True)
    for variable in ['thickness', 'bedTopography', 'sfcMassBal']:
        ds[variable] = (('Time', 'nCells'), np.ones((1, n_cells)))
    ds['layerThicknessFractions'] = (('nVertLevels',), np.ones(levels))
    return ds


def _make_dome_config(dome_type):
    config = PolarisConfigParser()
    config.add_from_package('polaris.tasks.landice.dome', 'dome.cfg')
    config.set('dome', 'dome_type', dome_type)
    return config
