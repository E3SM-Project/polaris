import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs import (
    BaseMeshStep,
    ScripStep,
    get_component_inputs_steps,
)
from polaris.tasks.e3sm.init.component_inputs.maps import CULLED_MESH_SUFFIXES
from polaris.tasks.e3sm.init.component_inputs.names import (
    SCRIP_REGIONS,
    get_mesh_short_name,
)
from polaris.tasks.mesh import mesh as mesh_component

MESH_NAME = 'u.oi30.lr10'
# a base mesh that is not a unified mesh, and so has no culled meshes to map
# to and no registered E3SM short name
SIMPLE_MESH_NAME = 'qu240km'

# the short names the unified mesh team has assigned so far
SHORT_NAMES = {
    'u.oi6to18.lr6to10': 'u01.oi6to18.lr6to10',
    'u.oi30.lr10': 'u02.oi30.lr10',
    'u.oi240.lr240': 'u03.oi240.lr240',
}


def test_the_steps_read_what_the_cull_step_writes():
    """
    Nothing here recomputes a culled mesh, a SCRIP description or an index
    map.  Each is declared as an input pointing into the cull step's work
    directory, which is what makes that true and keeps it true.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)
    cull_path = steps['cull_mesh'].path

    base_mesh = steps['staged_base_mesh']
    assert _targets(base_mesh) == {
        f'{prefix}_map_culled_to_base.nc': (
            f'{cull_path}/{prefix}_map_culled_to_base.nc'
        )
        for prefix in CULLED_MESH_SUFFIXES
    }

    scrip = steps['scrip']
    assert _targets(scrip) == {
        f'culled_{region}_mesh.scrip.nc': (
            f'{cull_path}/culled_{region}_mesh.scrip.nc'
        )
        for region in SCRIP_REGIONS
    }


def test_the_steps_are_shared_between_consumers():
    """
    Three tasks share most of these steps, so a second request has to hand
    back the same instances rather than a second copy of the work.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    again, config_again = get_component_inputs_steps(mesh_name=MESH_NAME)

    for name in ['staged_base_mesh', 'scrip']:
        assert again[name] is steps[name]
        assert e3sm_init.steps[steps[name].subdir] is steps[name]
    assert config_again is config


def test_the_steps_live_under_the_meshs_component_inputs_directory():
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    base = f'{MESH_NAME}/component_inputs'
    assert steps['staged_base_mesh'].subdir == f'{base}/base_mesh'
    assert steps['scrip'].subdir == f'{base}/scrip'


def test_a_culled_mesh_gets_the_index_maps():
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    base_mesh = steps['staged_base_mesh']
    assert base_mesh.with_maps
    assert base_mesh.outputs == ['base_mesh_with_maps.nc']


def test_a_mesh_outside_the_unified_family_gets_no_index_maps():
    """
    The gate is the mesh family, not a config option: a mesh that was not
    culled has no culled meshes to map to, and the file it writes should not
    promise maps that are not there.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=SIMPLE_MESH_NAME)

    base_mesh = steps['staged_base_mesh']
    assert not base_mesh.with_maps
    assert base_mesh.outputs == ['base_mesh.nc']
    assert not _targets(base_mesh)


@pytest.mark.parametrize('mesh_name', sorted(SHORT_NAMES))
def test_a_registered_mesh_resolves_its_short_name(mesh_name):
    """
    The short name comes from the mesh's own config, so setting up a unified
    mesh needs no ceremony.
    """
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=mesh_name)
    assert get_mesh_short_name(config) == SHORT_NAMES[mesh_name]


def test_the_test_only_mesh_is_marked_as_such():
    """
    u.oi.so12to30.lr10 is not headed for E3SM, so it has no assigned ID.  The
    XX placeholder is not a valid ID, which is what keeps anything staged
    under it from being mistaken for a released mesh.
    """
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name='u.oi.so12to30.lr10')
    assert get_mesh_short_name(config) == 'uXX.oi.so12to30.lr10'


def test_a_mesh_with_no_registered_short_name_says_which_option_to_set():
    """
    Only a person can decide a mesh has earned a short name, so an
    unregistered one has to fail rather than invent one -- and the message has
    to name the option, since there is nothing else to go on.
    """
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=SIMPLE_MESH_NAME)

    with pytest.raises(ValueError) as excinfo:
        get_mesh_short_name(config)
    message = str(excinfo.value)
    assert 'mesh_short_name' in message
    assert 'e3sm_short_name' in message


def test_setting_up_an_unregistered_mesh_fails_before_it_runs():
    """
    ScripStep resolves the short name at setup, so the failure lands before
    the workflow spends time on a mesh whose files cannot be named.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=SIMPLE_MESH_NAME)
    scrip = steps['scrip']

    with pytest.raises(ValueError, match='mesh_short_name'):
        get_mesh_short_name(scrip.config)

    config.set('component_inputs', 'mesh_short_name', 'q01.qu240km')
    assert get_mesh_short_name(scrip.config) == 'q01.qu240km'


def test_the_step_classes_are_what_the_factory_builds():
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)
    assert isinstance(steps['staged_base_mesh'], BaseMeshStep)
    assert isinstance(steps['scrip'], ScripStep)


def _targets(step):
    """The step's declared inputs, as {filename: work-directory target}."""
    return {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
        if entry['work_dir_target'] is not None
    }


def _reset_shared_components():
    for component in [e3sm_init, mesh_component]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
