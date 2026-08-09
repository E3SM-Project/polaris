import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
    ForwardStage,
    RealisticGlobalForward,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import CACHED_MESHES
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
    get_realistic_global_mesh_config,
)
from polaris.yaml import PolarisYaml


def test_add_realistic_global_tasks_registers_woa23():
    component = Ocean()

    add_realistic_global_tasks(component=component)

    task_subdir = 'spherical/realistic_global/hydrography/woa23'
    assert task_subdir in component.tasks
    old_task_subdir = f'{"global"}_ocean/hydrography/woa23'
    assert old_task_subdir not in component.tasks

    task = component.tasks[task_subdir]
    assert task.name == 'woa23'
    combine_topo_step_name = (
        'combine_topo_bedmap3_gebco2023_lat_lon_0.25000_degree'
    )
    assert list(task.steps) == [
        combine_topo_step_name,
        'combine',
        'extrapolate',
        'viz',
    ]
    assert task.step_symlinks[combine_topo_step_name] == 'combine_topo'
    assert 'spherical/realistic_global/hydrography/woa23/combine' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/extrapolate' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/viz' in (
        component.steps
    )


def test_add_realistic_global_tasks_registers_init_for_all_meshes():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    expected_mesh_names = list(get_base_mesh_step_names()) + list(
        UNIFIED_MESH_NAMES
    )
    for mesh_name in expected_mesh_names:
        task_subdir = f'spherical/realistic_global/{mesh_name}/init/task'
        assert task_subdir in component.tasks, (
            f'Expected init task for mesh={mesh_name!r} not found'
        )


def test_realistic_global_init_icos240km_steps():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    task_subdir = 'spherical/realistic_global/icos240km/init/task'
    assert task_subdir in component.tasks

    task = component.tasks[task_subdir]

    assert 'remap_woa23' in task.steps
    assert 'pstar_init' in task.steps
    assert 'initial_state' in task.steps
    assert 'cull_mesh' in task.steps
    assert 'extrapolate' in task.steps

    assert task.steps['remap_woa23'].subdir == (
        'spherical/realistic_global/icos240km/init/remap_woa23'
    )
    assert task.steps['pstar_init'].subdir == (
        'spherical/realistic_global/icos240km/init/pstar_init'
    )
    assert task.steps['initial_state'].subdir == (
        'spherical/realistic_global/icos240km/init/initial_state'
    )


def test_add_realistic_global_tasks_registers_forward_for_all_meshes():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    expected_mesh_names = list(get_base_mesh_step_names()) + list(
        UNIFIED_MESH_NAMES
    )
    for mesh_name in expected_mesh_names:
        task_subdir = f'spherical/realistic_global/{mesh_name}/forward/task'
        assert task_subdir in component.tasks, (
            f'Expected forward task for mesh={mesh_name!r} not found'
        )


def test_realistic_global_forward_icos240km_steps():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    task_subdir = 'spherical/realistic_global/icos240km/forward/task'
    assert task_subdir in component.tasks

    task = component.tasks[task_subdir]

    # the short forward run plus the shared init chain it depends on
    assert 'short' in task.steps
    assert 'initial_state' in task.steps
    assert 'pstar_init' in task.steps

    assert task.steps['short'].subdir == (
        'spherical/realistic_global/icos240km/forward/short'
    )
    # the init step is shared with the init task (same work dir)
    assert task.steps['initial_state'].subdir == (
        'spherical/realistic_global/icos240km/init/initial_state'
    )


def test_add_realistic_global_tasks_registers_cached_forward():
    """
    The cached tasks are the cheap members of the family: no init chain, so
    they can run without remapping WOA23 first.  They sit beside the
    init-chain task on the same mesh name, which is why the directory differs.
    """
    component = Ocean()
    add_realistic_global_tasks(component=component)

    for mesh_name in CACHED_MESHES:
        task_subdir = (
            f'spherical/realistic_global/{mesh_name}/cached_forward/task'
        )
        assert task_subdir in component.tasks, (
            f'Expected cached forward task for mesh={mesh_name!r} not found'
        )
        task = component.tasks[task_subdir]
        assert list(task.steps) == ['short', 'global_stats', 'viz']
        assert task.steps_to_run == ['short']


def test_cached_meshes_have_a_per_mesh_config():
    """
    The cached initial conditions were tuned with an explicit time step and
    run duration.  Without a per-mesh config the task would silently fall back
    to the shared defaults, which are scaled from a mesh minimum resolution
    these meshes do not report.
    """
    section = 'realistic_global_forward'
    for mesh_name, mesh_info in CACHED_MESHES.items():
        assert get_realistic_global_mesh_config(mesh_name) is not None, (
            f'No per-mesh config for mesh={mesh_name!r}'
        )
        # build the config the way the task does, so the assertions are about
        # what the run actually sees
        config = PolarisConfigParser()
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward',
            'realistic_global_forward.cfg',
        )
        assert add_realistic_global_mesh_config(config, mesh_name)
        config.combine()
        assert config.get(section, 'dt').strip()
        assert config.get(section, 'run_duration').strip()
        # both models advance the same way, so the comparison is like for like
        assert config.get(section, 'mpaso_time_integrator').strip() == 'RK4'
        assert config.get(section, 'omega_time_integrator').strip() == 'RK4'
        assert mesh_info['cell_count'] > 0


def test_cached_meshes_turn_off_what_omega_lacks():
    """
    The cached tasks exist to compare MPAS-Ocean with Omega, so MPAS-Ocean
    physics that Omega has no counterpart for only makes the two runs less
    comparable.  The init-chain tasks are the opposite case: they test the
    unified meshes in E3SM, so they want E3SM's physics.
    """
    section = 'realistic_global_forward'
    mpaso_only = ['use_GM', 'use_Redi', 'use_KPP', 'use_submesoscale']

    for mesh_name in CACHED_MESHES:
        stage = _stage_for_mesh(mesh_name)
        for option in mpaso_only:
            assert not getattr(stage, option), (
                f'{option} should be off on cached mesh {mesh_name!r}'
            )
        # blank leaves MPAS-Ocean's pressure_and_zmid, the counterpart to
        # Omega's Centered; Jacobian_from_TS has no Omega equivalent
        assert stage.pressure_gradient_type is None
        options = stage.mpaso_physics_options()
        assert not options['config_use_cvmix_kpp']
        assert not options['config_submesoscale_enable']
        assert 'config_pressure_gradient_type' not in options

    # the defaults, which every init-chain mesh gets, are the E3SM-like ones
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'realistic_global_forward.cfg',
    )
    config.combine()
    for option in mpaso_only:
        assert config.getboolean(section, option), (
            f'{option} should be on by default, for the E3SM-like runs'
        )
    assert (
        config.get(section, 'pressure_gradient_type').strip()
        == 'Jacobian_from_TS'
    )


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_cached_forward_model_config_renders(mesh_name, model):
    """
    Render the model config a cached task would run with, for both models.

    This is the closest a unit test gets to a `polaris setup` smoke check: it
    exercises the whole chain from per-mesh config through ForwardStage to the
    rendered yaml, without needing the cached initial condition to be
    downloaded first.
    """
    stage = _stage_for_mesh(mesh_name)
    replacements = stage.model_replacements(model, min_res=1.0)

    # both models advance the same way, on the tuned step
    assert replacements['dt'] == stage.dt
    expected_integrator = 'RungeKutta4' if model == 'omega' else 'RK4'
    assert replacements['time_integrator'] == expected_integrator
    assert replacements['run_duration'] == stage.run_duration

    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=replacements,
        model='Omega' if model == 'omega' else 'ocean',
    )
    if model == 'omega':
        global_stats = yaml.configs['Analysis']['GlobalStats']
        assert global_stats['SnapshotPeriod'] == [stage.stats_period()]
        assert global_stats['ReductionPeriod'] == []
    else:
        # the physics with no Omega counterpart is off, so the two models are
        # running as nearly the same configuration as they can
        options = stage.mpaso_physics_options()
        assert not options['config_use_GM']
        assert not options['config_use_Redi']
        assert not options['config_use_cvmix_kpp']
        assert not options['config_submesoscale_enable']
        assert 'config_pressure_gradient_type' not in options
        # nothing in forward.yaml puts them back
        for section in yaml.configs.values():
            assert 'config_use_cvmix_kpp' not in section
            assert 'config_submesoscale_enable' not in section
            assert 'config_pressure_gradient_type' not in section


def _stage_for_mesh(mesh_name):
    """The ForwardStage a task on ``mesh_name`` would build."""
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'realistic_global_forward.cfg',
    )
    add_realistic_global_mesh_config(config, mesh_name)
    config.combine()
    return ForwardStage.from_config(config)


def test_realistic_global_forward_without_init_steps():
    """
    The task is the same either way; only where the model inputs come from
    changes.  A source that downloads a cached initial condition brings no
    upstream steps with it, so the task is just the forward run, and its
    directory name keeps it apart from the init-chain task on the same mesh.
    """
    component = Ocean()
    init_condition = DatabaseInitialCondition(
        mesh_name='QU.240km',
        mpaso_id=151209,
        omega_id=260807,
        min_res=240.0,
        approx_cell_count=7153,
    )
    task = RealisticGlobalForward(
        component=component,
        mesh_name='QU.240km',
        init_condition=init_condition,
        subdir_name='cached_forward',
    )
    # the forward run and its two diagnostics, and nothing upstream of them
    assert list(task.steps) == ['short', 'global_stats', 'viz']
    assert task.subdir == (
        'spherical/realistic_global/QU.240km/cached_forward/task'
    )
    assert task.steps['short'].init_condition is init_condition
    # the diagnostics are diagnostics, not part of the run
    assert task.steps_to_run == ['short']


def test_realistic_global_init_one_task_per_mesh():
    """Exactly one task is registered per mesh (no model variants)."""
    component = Ocean()
    add_realistic_global_tasks(component=component)

    expected_mesh_names = list(get_base_mesh_step_names()) + list(
        UNIFIED_MESH_NAMES
    )
    for mesh_name in expected_mesh_names:
        task_subdir = f'spherical/realistic_global/{mesh_name}/init/task'
        assert task_subdir in component.tasks
        # Confirm there is no model-qualified variant
        for model in ('omega', 'mpas-ocean'):
            model_subdir = (
                f'spherical/realistic_global/{mesh_name}/init/{model}'
            )
            assert model_subdir not in component.tasks, (
                f'Unexpected per-model task found: {model_subdir!r}'
            )
