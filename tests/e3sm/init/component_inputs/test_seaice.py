import logging
import os

import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.seaice_initial_condition import (
    SeaiceInitialConditionStep,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'u.oi30.lr10'

SEAICE_STEPS = ['seaice_mesh', 'seaice_initial_condition']

LOGGER = logging.getLogger('test_seaice')


def test_the_seaice_steps_reach_no_ocean_step():
    """
    The claim D7 exists to make.  Walking the sea-ice steps' inputs and
    dependencies must never arrive at a step in the ocean component -- not the
    dynamic adjustment, not the initial state, not anything downstream of
    them.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)
    ocean_subdirs = set(ocean.steps)

    for name in SEAICE_STEPS:
        step = steps[name]
        assert not step.dependencies, name
        for entry in step.input_data:
            target = entry['work_dir_target']
            assert target is not None, name
            assert not target.startswith('ocean/'), (name, target)
            assert target not in ocean_subdirs, (name, target)


def test_the_seaice_steps_read_only_the_culled_mesh():
    """
    Compass read an ocean initial state and an ocean restart.  Reading the
    culled mesh instead is what removes the coupling, so the input list is
    worth pinning exactly rather than just checking it is ocean-free.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)
    cull_path = steps['cull_mesh'].path

    for name in SEAICE_STEPS:
        assert {
            entry['filename']: entry['work_dir_target']
            for entry in steps[name].input_data
        } == {'culled_ocean_mesh.nc': f'{cull_path}/culled_ocean_mesh.nc'}, (
            name
        )


def test_the_seaice_steps_belong_to_e3sm_init():
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    base = f'{MESH_NAME}/component_inputs'
    assert steps['seaice_mesh'].subdir == f'{base}/seaice_mesh'
    assert (
        steps['seaice_initial_condition'].subdir
        == f'{base}/seaice_initial_condition'
    )
    for name in SEAICE_STEPS:
        assert e3sm_init.steps[steps[name].subdir] is steps[name]


def test_the_coriolis_fields_are_computed_from_latitude(tmp_path):
    """
    2 * Omega * sin(lat) at cells, edges and vertices, rather than copied out
    of an ocean restart.  Latitudes chosen to cover both hemispheres, the
    equator and the poles.
    """
    lat = np.array([-0.5 * np.pi, -0.3, 0.0, 0.7, 0.5 * np.pi])
    ds_out = _run_seaice_initial_condition(_mesh(lat), tmp_path)

    omega = get_constant('angular_velocity')
    for field, dim in [
        ('fCell', 'nCells'),
        ('fEdge', 'nEdges'),
        ('fVertex', 'nVertices'),
    ]:
        assert ds_out[field].dims == (dim,), field
        np.testing.assert_allclose(
            ds_out[field].values, 2.0 * omega * np.sin(lat), atol=1e-20
        )


def test_the_coriolis_parameter_does_not_depend_on_longitude(tmp_path):
    """
    The rotated-sphere formula carries a cos(lon) term that vanishes only
    because the rotation angle is zero.  Two meshes differing only in
    longitude must come out identical, or the step is rotating the pole.
    """
    lat = np.array([-0.4, 0.0, 0.9])
    one = _run_seaice_initial_condition(_mesh(lat, lon=0.0), tmp_path / 'a')
    two = _run_seaice_initial_condition(_mesh(lat, lon=2.1), tmp_path / 'b')
    np.testing.assert_array_equal(one.fCell.values, two.fCell.values)


def test_the_coriolis_parameter_vanishes_on_the_equator(tmp_path):
    """
    The one value that would be indistinguishable from an unset field, so it
    is worth stating that it is meant.
    """
    ds_out = _run_seaice_initial_condition(_mesh(np.array([0.0])), tmp_path)
    assert ds_out.fCell.values[0] == 0.0
    # but not zero everywhere, which is what [coriolis] type = zero -- the
    # default of the option this step deliberately does not read -- would give
    poles = _run_seaice_initial_condition(
        _mesh(np.array([0.5 * np.pi])), tmp_path / 'pole'
    )
    assert poles.fCell.values[0] != 0.0


def test_the_mesh_is_carried_through_unchanged(tmp_path):
    """
    The initial condition adds Coriolis to the mesh; it must not drop
    anything the mesh already had.
    """
    ds = _mesh(np.array([0.1, 0.2, 0.3]))
    ds['areaCell'] = ('nCells', np.array([1.0, 2.0, 3.0]))
    ds['indexToCellID'] = ('nCells', np.array([1, 2, 3]))

    ds_out = _run_seaice_initial_condition(ds, tmp_path)
    for var in ds.data_vars:
        np.testing.assert_array_equal(ds_out[var].values, ds[var].values)


def _mesh(lat, lon=None):
    """
    A minimal horizontal mesh at the given latitudes.

    Longitudes vary across the mesh by default, so a formula that wrongly
    depended on them would not come out uniform by accident.
    """
    if lon is None:
        lon_values = np.linspace(0.0, 2.0 * np.pi, lat.size, endpoint=False)
    else:
        lon_values = np.full(lat.size, lon)
    return xr.Dataset(
        {
            'latCell': ('nCells', lat),
            'lonCell': ('nCells', lon_values),
            'latEdge': ('nEdges', lat),
            'lonEdge': ('nEdges', lon_values),
            'latVertex': ('nVertices', lat),
            'lonVertex': ('nVertices', lon_values),
        }
    )


def _run_seaice_initial_condition(ds_mesh, tmp_path):
    """
    Actually run the step over a hand-built mesh, and read back what it wrote.

    Driving the step rather than calling the Coriolis helper directly is what
    makes these tests about the staged file: a step that stopped adding
    Coriolis, or started copying it from somewhere, would fail here.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    step = steps['seaice_initial_condition']
    assert isinstance(step, SeaiceInitialConditionStep)

    step.config = config
    step.logger = LOGGER

    os.makedirs(tmp_path, exist_ok=True)
    ds_mesh.to_netcdf(tmp_path / 'culled_ocean_mesh.nc')
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.run()
        with xr.open_dataset('seaice_initial_condition.nc') as ds_out:
            return ds_out.load()
    finally:
        os.chdir(cwd)


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
