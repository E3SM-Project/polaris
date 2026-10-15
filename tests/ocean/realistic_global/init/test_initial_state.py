import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.init.initial_state import (
    InitialStateStep,
)


class _FakePStarInitStep:
    path = 'fake/pstar_init'


class _FakeCullMeshStep:
    path = 'fake/cull_mesh'


def _make_step(model):
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'realistic_global_init.cfg',
    )
    config.set('ocean', 'model', model)

    component = Ocean()
    component.model = model
    component._read_var_map()

    step = InitialStateStep(
        component=component,
        subdir='init/initial_state',
        pstar_init_step=_FakePStarInitStep(),
        cull_mesh_step=_FakeCullMeshStep(),
    )
    step.config = config
    step.setup()
    return step


def _input_by_filename(step, filename):
    matches = [
        entry for entry in step.input_data if entry['filename'] == filename
    ]
    assert len(matches) == 1, f'expected exactly one {filename} input'
    return matches[0]


@pytest.mark.parametrize('model', ['omega', 'mpas-ocean'])
def test_reconstruction_weights_come_from_the_culled_mesh(model):
    """
    Omega reads the cell-centered vector-reconstruction fields from the
    horizontal mesh, and ``write_horiz_mesh_dataset()`` merges them in from
    ``reconstruction_weights.nc`` in the step's work directory.  The weights
    have to be the culled ocean mesh's, not the base mesh's, since the
    initial condition is built on the culled mesh.
    """
    step = _make_step(model)
    entry = _input_by_filename(step, 'reconstruction_weights.nc')
    assert entry['work_dir_target'] == (
        'fake/cull_mesh/culled_ocean_reconstruction_weights.nc'
    )


@pytest.mark.parametrize('model', ['omega', 'mpas-ocean'])
def test_mesh_and_graph_come_from_the_culled_mesh(model):
    """
    The mesh and graph the model runs on are the culled ocean mesh's, which
    is what the reconstruction weights above have to match.
    """
    step = _make_step(model)
    assert _input_by_filename(step, 'culled_mesh.nc')['work_dir_target'] == (
        'fake/cull_mesh/culled_ocean_mesh.nc'
    )
    assert _input_by_filename(step, 'culled_graph.info')[
        'work_dir_target'
    ] == ('fake/cull_mesh/culled_ocean_graph.info')
