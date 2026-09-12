"""
Tests that the mesh, vertical-coordinate and initial-state files an ocean
init step writes pass the CF checker with no errors and no warnings, for
both models.  The baroclinic channel init step is run for real on a coarse
mesh, since the metadata only shows up in the files it writes.
"""

import logging
import os

import pytest
import xarray as xr

from polaris.cf_check import CF_TABLES, check_cf_compliance
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.baroclinic_channel.init import Init
from tests.test_cf_check import AREA_TYPES, REGION_NAMES, STANDARD_NAMES

# the files the step declares for the CF check, per model
CHECKED_FILES = {
    'mpas-ocean': ['base_mesh.nc', 'culled_mesh.nc', 'init.nc'],
    'omega': ['base_mesh.nc', 'culled_mesh.nc', 'vert_coord.nc', 'init.nc'],
}


def _make_config(model):
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.baroclinic_channel', 'baroclinic_channel.cfg'
    )
    # the baroclinic channel tasks use a linear equation of state
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.set('ocean', 'model', model)
    # keep the test cheap; the metadata does not depend on the grid
    config.set('vertical_grid', 'vert_levels', '3')
    return config


@pytest.fixture(scope='module', params=['mpas-ocean', 'omega'])
def init_outputs(request, tmp_path_factory):
    """Run the init step once per model and return the model name and the
    directory the step wrote its files to, with the CF tables in it"""
    model = request.param

    component = Ocean()
    component.model = model
    component._read_variables_yaml()
    if model == 'omega':
        component._read_var_map()

    step = Init(component=component, resolution=40.0, indir='init')
    step.config = _make_config(model)
    step.logger = logging.getLogger(f'baroclinic_channel_init_{model}')

    workdir = tmp_path_factory.mktemp(f'baroclinic_channel_init_{model}')
    for (_, filename), contents in zip(
        CF_TABLES, [STANDARD_NAMES, AREA_TYPES, REGION_NAMES], strict=True
    ):
        (workdir / filename).write_text(contents)
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        step.run()
    finally:
        os.chdir(cwd)

    return model, str(workdir)


def test_init_variables_are_labelled_as_themselves(init_outputs):
    """A state variable made from a mesh variable with ones_like() must not
    keep the mesh variable's description"""
    model, workdir = init_outputs
    with xr.open_dataset(os.path.join(workdir, 'init.nc')) as ds_init:
        for name, da in ds_init.data_vars.items():
            long_name = da.attrs['long_name']
            assert 'coordinates of' not in long_name, f'{name}: {long_name}'


def test_init_files_pass_the_cf_check(init_outputs):
    """No errors, which would fail the step, and no warnings either, so
    that every variable is described"""
    model, workdir = init_outputs
    results = check_cf_compliance(CHECKED_FILES[model], workdir)
    for result in results:
        assert result['passed'], result['report']
        assert result['warnings'] == 0, result['report']
