import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.models import (
    check_ocean_model,
    check_seaice_model,
)
from polaris.tasks.e3sm.init.component_inputs.ocean_graph_partition import (
    GRAPH_BASENAME,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'u-oi30-lr10'


def test_the_initial_condition_comes_from_the_adjusted_restart():
    """
    Not from the initial state.  The dynamic adjustment exists to dissipate
    the fast waves an interpolated initial condition sets off, so staging
    init.nc would hand every E3SM run that transient back.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_initial_condition']
    (source,) = [
        entry['work_dir_target']
        for entry in step.input_data
        if entry['filename'] == 'restart.nc'
    ]
    assert '/dynamic_adjustment/restarts/' in source
    assert source.endswith('.nc')
    assert 'initial_state' not in source


def test_the_initial_condition_depends_on_the_last_stage():
    """
    The restart is named from the schedule rather than from the step, so the
    ordering cannot be inferred from the filename and has to be declared.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_initial_condition']
    assert list(step.dependencies) == ['simulation']
    assert step.forward_step is steps['simulation']


def test_the_ocean_steps_reuse_the_shared_adjustment_chain():
    """
    Asking for component inputs must not build a second copy of a chain that
    takes hours to run.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    for name in ['initial_state', 'simulation']:
        assert ocean.steps[steps[name].subdir] is steps[name]
    # and the staging steps belong to e3sm/init, not to the ocean
    for name in ['ocean_mesh', 'ocean_initial_condition']:
        assert e3sm_init.steps[steps[name].subdir] is steps[name]


def test_the_ocean_mesh_reads_the_initial_state():
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_mesh']
    init_path = steps['initial_state'].path
    assert {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    } == {
        'mesh.nc': f'{init_path}/mesh.nc',
        'init.nc': f'{init_path}/init.nc',
    }


def test_the_partitions_come_from_the_ocean_graph():
    """
    The ``ocean`` prefix, matching the domain the initial condition is built
    on -- not ``ocean_no_cavities``, which exists for mapping files.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_graph_partition']
    (source,) = [entry['work_dir_target'] for entry in step.input_data]
    assert source.endswith('culled_ocean_graph.info')


def test_the_partition_names_carry_no_creation_date():
    """
    The date belongs to staging.  gpmetis names its output after its input,
    so a date here would bake setup-time state into the step's own files.
    """
    assert GRAPH_BASENAME == 'mpas-o.graph.info'


def test_omega_raises_rather_than_staging_something_wrong():
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=MESH_NAME)

    config.set('component_inputs', 'ocean_model', 'omega')
    with pytest.raises(NotImplementedError, match='Omega'):
        check_ocean_model(config)


def test_an_unknown_model_is_rejected():
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=MESH_NAME)

    config.set('component_inputs', 'ocean_model', 'hycom')
    with pytest.raises(ValueError, match='hycom'):
        check_ocean_model(config)

    config.set('component_inputs', 'ocean_model', 'mpas-ocean')
    config.set('component_inputs', 'seaice_model', 'cice')
    with pytest.raises(ValueError, match='cice'):
        check_seaice_model(config)


def test_the_default_models_are_the_supported_ones():
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    assert check_ocean_model(config) == 'mpas-ocean'
    assert check_seaice_model(config) == 'mpas-seaice'


def test_sea_ice_can_be_turned_off_without_touching_the_ocean():
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    config.set('component_inputs', 'seaice_model', 'none')
    assert check_seaice_model(config) == 'none'
    assert check_ocean_model(config) == 'mpas-ocean'


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()


#: The gpmetis task count above which Compass saw failures, recorded in
#: compass/ocean/tests/global_ocean/mesh/rrs6to18/rrs6to18.cfg.
GPMETIS_TASK_LIMIT = 750000

#: Cells in each mesh's culled ocean domain, measured from the 2026-08-11
#: runs, and the 2026-10-20 runs for the u-oi6to18 meshes.  Used to check the
#: partition bounds without building a mesh.
CULLED_OCEAN_CELLS = {
    'u-oi240-lr240': 7330,
    'u-oi30-lr10': 462646,
    'u-oi-so12to30-lr10': 794276,
    'u-oi6to18-lr12p5': 4016105,
    'u-oi6to18-lr25': 4017697,
}


@pytest.mark.parametrize('mesh_name', sorted(CULLED_OCEAN_CELLS))
def test_no_mesh_asks_gpmetis_for_more_parts_than_it_can_do(mesh_name):
    """
    The largest partition is ncells / min_cells_per_core, and gpmetis fails
    above roughly 750,000 parts.  Only the u-oi6to18 meshes are large enough
    for the default floor of 2 to cross that, which is why they are the meshes
    with an override -- exactly as rrs6to18 is the only one in Compass.
    """
    _reset_shared_components()
    _, config = get_component_inputs_steps(mesh_name=mesh_name, target='ocean')

    min_cells_per_core = config.getint(
        'component_inputs', 'min_cells_per_core'
    )
    largest = CULLED_OCEAN_CELLS[mesh_name] // min_cells_per_core

    assert largest <= GPMETIS_TASK_LIMIT, (
        f'{mesh_name} would ask gpmetis for {largest} parts; raise '
        f'[component_inputs] min_cells_per_core in its config'
    )


def test_only_the_meshes_that_need_it_override_the_floor():
    """
    The override costs partitions that a smaller mesh has no reason to lose,
    so it belongs only where the limit bites.
    """
    for mesh_name in ['u-oi6to18-lr12p5', 'u-oi6to18-lr25']:
        _reset_shared_components()
        _, config = get_component_inputs_steps(
            mesh_name=mesh_name, target='ocean'
        )
        assert config.getint('component_inputs', 'min_cells_per_core') == 6
        assert config.getint('component_inputs', 'max_cells_per_core') == 30000

    for mesh_name in ['u-oi240-lr240', 'u-oi30-lr10']:
        _reset_shared_components()
        _, config = get_component_inputs_steps(
            mesh_name=mesh_name, target='ocean'
        )
        assert config.getint('component_inputs', 'min_cells_per_core') == 2
