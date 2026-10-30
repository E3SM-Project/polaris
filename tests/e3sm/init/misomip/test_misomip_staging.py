import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.component import Component
from polaris.e3sm.init.inputdata import ASSEMBLED_FILES
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.misomip import (
    MisomipTask,
    get_misomip_experiment_steps,
)
from polaris.tasks.e3sm.init.misomip.names import INPUTS_SECTION
from polaris.tasks.e3sm.init.misomip.ocean_initial_condition import (
    OceanInitialConditionStep,
)
from polaris.tasks.landice import landice
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'misomip-o4km-li1km'
OCEAN_GRID = 'misomip-o4km'
LANDICE_GRID = 'misomip-li1km'
CREATION_DATE = '20250101'
NCORES = [1, 8, 36]

LOGGER = logging.getLogger('test_misomip_staging')


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean, landice]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()


def _run_assemble(tmp_path, experiment, creation_date=CREATION_DATE):
    """
    Run an experiment's assembly step over fake products, and list what it
    staged
    """
    _reset_shared_components()
    steps, config = get_misomip_experiment_steps(MESH_NAME, experiment)
    step = steps['assemble']

    config.set(INPUTS_SECTION, 'creation_date', creation_date)
    step.config = config
    step.logger = LOGGER
    # three levels below the pair's directory, as the step is in a run, so
    # the partition steps' directories are found beside it
    step.work_dir = str(tmp_path / 'misomip' / experiment / 'assemble')
    os.makedirs(step.work_dir, exist_ok=True)

    for entry in step.input_data:
        path = os.path.join(step.work_dir, entry['filename'])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(entry['filename'])

    for name, basename in [
        ('ocean_partitions', 'mpas-o.graph.info'),
        ('landice_partitions', 'mpasli.graph.info'),
    ]:
        part_dir = tmp_path / name
        part_dir.mkdir(exist_ok=True)
        for ncores in NCORES:
            (part_dir / f'{basename}.part.{ncores}').write_text('')

    cwd = os.getcwd()
    try:
        os.chdir(step.work_dir)
        step.run()
    finally:
        os.chdir(cwd)

    root = os.path.join(step.work_dir, ASSEMBLED_FILES)
    staged = set()
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            staged.add(os.path.relpath(os.path.join(dirpath, filename), root))
    return staged, root


def _expected(experiment, initial_conditions=True, data_mode=False):
    ocn = f'inputdata/ocn/mpas-o/{OCEAN_GRID}'
    glc = f'inputdata/glc/mpasli/{LANDICE_GRID}'
    maps = 'inputdata/cpl/gridmaps'
    date = CREATION_DATE
    expected = {
        'README',
        f'{ocn}/mpaso.{OCEAN_GRID}.{experiment}_forcing.{date}.nc',
        f'{ocn}/{OCEAN_GRID}.scrip.{date}.nc',
        f'{glc}/{LANDICE_GRID}.scrip.{date}.nc',
        f'{maps}/{OCEAN_GRID}/map_{OCEAN_GRID}_to_{LANDICE_GRID}_aave.'
        f'{date}.nc',
        f'{maps}/{LANDICE_GRID}/map_{LANDICE_GRID}_to_{OCEAN_GRID}_aave.'
        f'{date}.nc',
    }
    expected |= {
        f'{ocn}/partitions/mpas-o.graph.info.{date}.part.{n}' for n in NCORES
    }
    expected |= {f'{glc}/mpasli.graph.info.{date}.part.{n}' for n in NCORES}
    if initial_conditions:
        expected |= {
            f'{ocn}/mpaso.{OCEAN_GRID}.{experiment}.{date}.nc',
            f'{glc}/{LANDICE_GRID}.{experiment}.{date}.nc',
        }
    if data_mode:
        expected.add(f'{glc}/{LANDICE_GRID}.{experiment}_datamode.{date}.nc')
    return expected


@pytest.mark.parametrize(
    'experiment, initial_conditions, data_mode',
    [
        ('ocean0', True, False),
        ('ocean3', True, True),
        ('iceocean1r', True, False),
        ('iceocean1ra', False, False),
    ],
)
def test_every_product_lands_at_its_e3sm_path(
    tmp_path, experiment, initial_conditions, data_mode
):
    staged, _ = _run_assemble(tmp_path, experiment)
    assert staged == _expected(experiment, initial_conditions, data_mode)


def test_the_staged_files_point_at_the_products(tmp_path):
    _, root = _run_assemble(tmp_path, 'ocean0')
    path = os.path.join(
        root,
        f'inputdata/ocn/mpas-o/{OCEAN_GRID}',
        f'mpaso.{OCEAN_GRID}.ocean0.{CREATION_DATE}.nc',
    )
    assert os.path.islink(path)
    assert os.path.realpath(path).endswith(
        'ocean_initial_condition__ocean_initial_condition.nc'
    )


def test_the_assembly_waits_for_the_partitions():
    _reset_shared_components()
    steps, _ = get_misomip_experiment_steps(MESH_NAME, 'ocean0')
    dependencies = steps['assemble'].dependencies
    assert dependencies['ocean_partitions'] is steps['ocean_partitions']
    assert dependencies['landice_partitions'] is steps['landice_partitions']


def test_the_creation_date_is_fixed_at_setup():
    _reset_shared_components()
    task = MisomipTask(
        component=Component(name='e3sm/init'),
        mesh_name=MESH_NAME,
        experiment='ocean0',
    )
    assert task.config.get(INPUTS_SECTION, 'creation_date').strip() == ''
    task.configure()
    first = task.config.get(INPUTS_SECTION, 'creation_date')
    assert first != ''
    task.configure()
    assert task.config.get(INPUTS_SECTION, 'creation_date') == first


def test_the_ocean_initial_condition_holds_the_mesh_and_state(tmp_path):
    ds_mesh = xr.Dataset(
        {
            'xCell': ('nCells', np.array([0.0, 1.0])),
            'areaCell': ('nCells', np.array([2.0, 2.0])),
        },
        attrs={'sphere_radius': 6371220.0},
    )
    ds_state = xr.Dataset(
        {
            'xtime': ('Time', np.array([b'0001-01-11_00:00:00'])),
            'ssh': (('Time', 'nCells'), np.array([[-1.0, -2.0]])),
            'xCell': ('nCells', np.array([0.0, 1.0])),
        }
    )
    ds_mesh.to_netcdf(tmp_path / 'mesh.nc')
    ds_state.to_netcdf(tmp_path / 'state.nc')

    step = OceanInitialConditionStep(
        component=Component(name='e3sm/init'),
        subdir='ocean_initial_condition',
        init_step=_Path('init'),
        ssh_adjust_step=_Path('ssh_adjust_9'),
    )
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.run()
    finally:
        os.chdir(cwd)

    with xr.open_dataset(tmp_path / 'ocean_initial_condition.nc') as ds:
        assert 'xtime' not in ds
        assert ds.attrs['sphere_radius'] == 6371220.0
        np.testing.assert_array_equal(ds.areaCell, [2.0, 2.0])
        np.testing.assert_array_equal(ds.ssh, [[-1.0, -2.0]])


class _Path:
    def __init__(self, path):
        self.path = path
