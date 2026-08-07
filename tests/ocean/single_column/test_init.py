"""
Tests that the single-column init step keeps the initial state and the
forcing in separate files.

The step is run for real (it builds a tiny 4x4 mesh with a handful of
vertical levels), since the split only shows up in the files it writes.
"""

import logging
import os

import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.single_column.init import Init

# fields the model reads as forcing, in MPAS-Ocean and Omega names
FORCING_VARS = {
    'mpas-ocean': ['windStressZonal', 'windStressMeridional'],
    'omega': ['SfcStressZonal', 'SfcStressMeridional'],
}

# initial-state fields, which belong in the initial condition alone
STATE_VARS = {
    'mpas-ocean': [
        'temperature',
        'salinity',
        'layerThickness',
        'normalVelocity',
    ],
    'omega': [
        'Temperature',
        'Salinity',
        'PseudoThickness',
        'SurfacePressure',
        'NormalVelocity',
    ],
}

# vertical coordinate fields, which Omega reads from its own file
VERT_COORD_VARS = {
    'mpas-ocean': ['bottomDepth', 'restingThickness'],
    'omega': ['BottomGeomDepth', 'RefPseudoThickness'],
}


def _make_config(model):
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.single_column', 'single_column.cfg'
    )
    # the wind stress is what the ekman task reads from the forcing file
    config.add_from_package('polaris.tasks.ocean.single_column', 'wind.cfg')
    # the single-column tasks all use a linear equation of state
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.set('ocean', 'model', model)
    # keep the test cheap; the split does not depend on the vertical grid
    config.set('vertical_grid', 'vert_levels', '4')
    return config


@pytest.fixture(scope='module', params=['mpas-ocean', 'omega'])
def init_outputs(request, tmp_path_factory):
    """Run the init step once per model and return the model name and the
    directory the step wrote its files to."""
    model = request.param

    component = Ocean()
    component.model = model
    component._read_variables_yaml()
    if model == 'omega':
        component._read_var_map()

    step = Init(component=component, subdir='init')
    step.config = _make_config(model)
    step.logger = logging.getLogger(f'single_column_init_{model}')

    workdir = tmp_path_factory.mktemp(f'single_column_init_{model}')
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        step.run()
    finally:
        os.chdir(cwd)

    return model, workdir


def test_forcing_file_has_only_forcing(init_outputs):
    """The forcing file must not carry the mesh, the vertical coordinate or
    the model state.  For Omega, a layer thickness in the forcing dataset
    would send write_model_dataset() looking for a surface pressure that
    only the initial state has."""
    model, workdir = init_outputs

    with xr.open_dataset(workdir / 'forcing.nc') as ds_forcing:
        for var in FORCING_VARS[model]:
            assert var in ds_forcing
        for var in STATE_VARS[model] + VERT_COORD_VARS[model]:
            assert var not in ds_forcing
        # a horizontal mesh variable stands in for the mesh as a whole
        assert 'xCell' not in ds_forcing


def test_initial_state_file_has_no_forcing(init_outputs):
    """The forcing fields belong in the forcing file alone, and the state
    fields in the initial condition."""
    model, workdir = init_outputs

    with xr.open_dataset(workdir / 'init.nc') as ds_init:
        for var in FORCING_VARS[model]:
            assert var not in ds_init
        assert 'temperatureSurfaceRestoringValue' not in ds_init
        for var in STATE_VARS[model]:
            assert var in ds_init


def test_surface_restoring_climatology_goes_with_the_initial_state(
    init_outputs,
):
    """In Omega, TracersMonthlySurfClimoCell is an auxiliary state variable
    registered in the AuxiliaryState field group, and the Forcing stream is
    read before those fields are defined.  It has to travel with the initial
    state, not with the forcing.  It has no MPAS-Ocean equivalent, so it is
    not written at all for MPAS-Ocean."""
    model, workdir = init_outputs

    with xr.open_dataset(workdir / 'init.nc') as ds_init:
        assert ('TracersMonthlySurfClimoCell' in ds_init) == (model == 'omega')
    with xr.open_dataset(workdir / 'forcing.nc') as ds_forcing:
        assert 'TracersMonthlySurfClimoCell' not in ds_forcing
