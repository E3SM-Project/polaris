import dataclasses
import importlib.resources as imp_res
from configparser import ConfigParser
from typing import cast

import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.forward import (
    TIME_INTEGRATORS,
    DatabaseInitialCondition,
    ForwardStage,
    RealisticGlobalForward,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import CACHED_MESHES
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
)
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
        f'{combine_topo_step_name}_prepare',
        f'{combine_topo_step_name}_weights',
        combine_topo_step_name,
        'combine',
        'extrapolate',
        'viz',
    ]
    assert task.step_symlinks[combine_topo_step_name] == 'combine_topo'
    assert (
        task.step_symlinks[f'{combine_topo_step_name}_prepare']
        == 'combine_topo_prepare'
    )
    assert 'spherical/realistic_global/hydrography/woa23/combine' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/extrapolate' in (
        component.steps
    )
    assert 'spherical/realistic_global/hydrography/woa23/viz' in (
        component.steps
    )
    # the standalone task regenerates the product rather than reading it
    # from the cache, and plots it only on request
    assert task.free_running_steps == {
        'spherical/realistic_global/hydrography/woa23/combine',
        'spherical/realistic_global/hydrography/woa23/extrapolate',
    }
    assert 'viz' not in task.steps_to_run


def test_woa23_steps_hand_back_the_config_their_steps_use():
    component = Ocean()

    first_steps, first_config = get_woa23_steps(component=component)
    second_steps, second_config = get_woa23_steps(component=component)

    assert second_config is first_config
    for name, step in first_steps.items():
        assert second_steps[name] is step, name
        if not name.startswith('combine_topo'):
            # the combined topography steps are e3sm/init steps with their own
            # config
            assert step.config is first_config, name
    # and re-registering what was handed back is a no-op rather than an error
    component.add_config(second_config)


def test_add_realistic_global_tasks_registers_jra55():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    task = component.tasks['spherical/realistic_global/forcing/jra55']
    # the standalone task regenerates the cached product and plots it
    assert task.free_running_steps == {
        'spherical/realistic_global/forcing/jra55/stress'
    }
    assert task.steps_to_run == ['stress', 'viz']


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
        for time_integrator in TIME_INTEGRATORS:
            task_subdir = (
                f'spherical/realistic_global/{mesh_name}/forward/'
                f'{time_integrator}/task'
            )
            assert task_subdir in component.tasks, (
                f'Expected forward task for mesh={mesh_name!r} not found'
            )


def test_realistic_global_forward_icos240km_steps():
    component = Ocean()
    add_realistic_global_tasks(component=component)

    task_subdir = (
        'spherical/realistic_global/icos240km/forward/split_explicit/task'
    )
    assert task_subdir in component.tasks

    task = component.tasks[task_subdir]

    # the short forward run plus the shared init chain it depends on
    assert 'short' in task.steps
    assert 'initial_state' in task.steps
    assert 'pstar_init' in task.steps

    assert task.steps['short'].subdir == (
        'spherical/realistic_global/icos240km/forward/split_explicit/short'
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
        for time_integrator in TIME_INTEGRATORS:
            task_subdir = (
                f'spherical/realistic_global/{mesh_name}/cached_forward/'
                f'{time_integrator}/task'
            )
            assert task_subdir in component.tasks, (
                f'Expected cached forward task for mesh={mesh_name!r} not '
                f'found'
            )
            task = component.tasks[task_subdir]
            assert list(task.steps) == ['short', 'global_stats', 'viz']
            assert task.steps_to_run == ['short']


def test_cached_meshes_have_a_per_mesh_config():
    """
    The cached initial conditions were tuned with explicit time steps and a
    run duration.  Without a per-mesh config the task would silently fall back
    to the shared defaults, which are scaled from a mesh minimum resolution
    these meshes do not report.  Each needs a split step and an RK4 one, for
    the two variants of the task.
    """
    section = 'realistic_global_forward'
    for mesh_name, mesh_info in CACHED_MESHES.items():
        assert get_realistic_global_mesh_config(mesh_name) is not None, (
            f'No per-mesh config for mesh={mesh_name!r}'
        )
        # build the config the way the task does, so the assertions are about
        # what the run actually sees
        config = _variant_config(mesh_name, 'split_explicit')
        for option in ['dt', 'btr_dt', 'rk4_dt', 'run_duration']:
            assert config.get(section, option).strip(), (
                f'No {option} for mesh={mesh_name!r}'
            )
        assert mesh_info['cell_count'] > 0


@pytest.mark.parametrize('mesh_name', ['QU.240km', 'u-oi240-lr240'])
def test_the_variants_choose_the_integrators(mesh_name):
    """
    The split_explicit variant takes the defaults, a split integrator for
    each model, and the rk4 variant runs RK4 in both, so that the two models
    advance the same way.
    """
    section = 'realistic_global_forward'
    config = _variant_config(mesh_name, 'split_explicit')
    assert config.get(section, 'mpaso_time_integrator') == 'split_explicit_ab2'
    assert config.get(section, 'omega_time_integrator') == 'split_explicit'
    config = _variant_config(mesh_name, 'rk4')
    assert config.get(section, 'mpaso_time_integrator') == 'RK4'
    assert config.get(section, 'omega_time_integrator') == 'RK4'


def test_an_unknown_variant_is_rejected():
    with pytest.raises(ValueError, match='time_integrator'):
        RealisticGlobalForward(
            component=Ocean(),
            mesh_name='QU.240km',
            init_condition=_qu240_database_ic(),
            subdir_name='cached_forward',
            time_integrator='split_explicit_ab2',
        )


@pytest.mark.parametrize(
    'mesh_name, mom_del2, mom_del4',
    [('QU.240km', 1.0e3, 1.0e15), ('EC30to60E2r2', 1.0e4, 1.2e11)],
)
def test_cached_meshes_take_the_one_year_runs_viscosities(
    mesh_name, mom_del2, mom_del4
):
    for time_integrator in TIME_INTEGRATORS:
        stage = _stage_for_mesh(mesh_name, time_integrator)
        assert stage.mom_del2 == mom_del2
        assert stage.mom_del4 == mom_del4


# the MPAS-Ocean physics production runs have and Omega does not
_MPASO_ONLY_PHYSICS = ['use_GM', 'use_Redi', 'use_submesoscale']


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
def test_cached_meshes_run_production_physics(mesh_name):
    """
    A cached initial condition does not change the physics: like every other
    forward run, the cached tasks run as close to production as each model
    allows.  Comparing MPAS-Ocean with Omega is opt-in, through
    compare_with_omega.cfg.
    """
    stage = _stage_for_mesh(mesh_name)
    for option in _MPASO_ONLY_PHYSICS:
        assert getattr(stage, option), (
            f'{option} should be on for cached mesh {mesh_name!r}'
        )
    assert stage.pressure_gradient_type == 'Jacobian_from_TS'
    assert stage.vert_mixing_options()['config_use_cvmix_kpp']


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES) + ['qu240km'])
def test_compare_with_omega_cfg_turns_off_what_omega_lacks(mesh_name):
    """
    Polaris never reads compare_with_omega.cfg itself; a user layers it on
    to compare the two models.  It must turn off the MPAS-Ocean physics Omega
    does not have, and nothing in it may be a misspelled option.
    """
    reference = imp_res.files(
        'polaris.tasks.ocean.realistic_global.forward'
    ).joinpath('compare_with_omega.cfg')
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward', 'forward.cfg'
    )
    add_realistic_global_mesh_config(config, mesh_name)
    config.add_user_config(str(reference))
    config.combine()

    reference_config = ConfigParser()
    reference_config.read(str(reference))
    section = 'realistic_global_forward'
    stage_fields = {
        field.name.lower() for field in dataclasses.fields(ForwardStage)
    }
    for option in reference_config.options(section):
        assert option in stage_fields, option

    stage = ForwardStage.from_config(config)
    for option in _MPASO_ONLY_PHYSICS:
        assert not getattr(stage, option), option
    assert stage.pressure_gradient_type == 'pressure_and_zmid'
    # KPP is in both models, so a comparison keeps it
    assert stage.vert_mixing_options()['config_use_cvmix_kpp']


@pytest.mark.parametrize('time_integrator', TIME_INTEGRATORS)
@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_cached_forward_model_config_renders(
    mesh_name, model, time_integrator
):
    """
    Render the model config a cached task would run with, for both models.

    This is the closest a unit test gets to a `polaris setup` smoke check: it
    exercises the whole chain from per-mesh config through ForwardStage to the
    rendered yaml, without needing the cached initial condition to be
    downloaded first.
    """
    stage = _stage_for_mesh(mesh_name, time_integrator)
    replacements = stage.model_replacements(model, min_res=1.0)

    # each variant advances on the step tuned for it
    if time_integrator == 'rk4':
        assert replacements['dt'] == stage.rk4_dt
        expected_integrator = 'RungeKutta4' if model == 'omega' else 'RK4'
    else:
        assert replacements['dt'] == stage.dt
        assert replacements['btr_dt'] == stage.btr_dt
        expected_integrator = (
            'SplitExplicitRK2' if model == 'omega' else 'split_explicit_ab2'
        )
    assert replacements['time_integrator'] == expected_integrator
    assert replacements['run_duration'] == stage.run_duration
    # both models have the KPP boundary layer, and both are told so
    assert stage.vert_mixing_options() == {'config_use_cvmix_kpp': True}

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
        # production physics, as for every other forward run
        options = stage.mpaso_physics_options()
        assert options['config_use_GM']
        assert options['config_use_Redi']
        assert options['config_submesoscale_enable']
        assert options['config_pressure_gradient_type'] == 'Jacobian_from_TS'


class _ConfigOnlyStep:
    """
    A stand-in for the forward step that carries a real task config.

    The point is the config: an InitialCondition reads whatever it needs from
    it, and a fake that supplies those options itself cannot tell whether the
    task's own config file actually provides them.
    """

    def __init__(self, config):
        self.config = config
        self.calls = []

    def add_horiz_mesh_input_file(self, **kwargs):
        self.calls.append(('horiz_mesh', kwargs))

    def add_vert_coord_input_file(self, **kwargs):
        self.calls.append(('vert_coord', kwargs))

    def add_init_input_file(self, **kwargs):
        self.calls.append(('init', kwargs))

    def add_input_file(self, **kwargs):
        self.calls.append((kwargs.get('filename'), kwargs))

    def get_init_filename(self):
        return self.config.get('ocean_staged_files', 'init_filename')


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_cached_task_config_has_what_the_database_source_needs(
    mesh_name, model
):
    """
    Build the config the task builds, and let the initial condition read from
    it.  A missing option here is a setup-time crash on a real machine, which
    is what happened when [ocean] eos_type lived only in a config file that
    the cached tasks stopped including.
    """
    config = _task_config(mesh_name, model)
    init_condition = DatabaseInitialCondition(
        mesh_name=mesh_name,
        mpaso_id=CACHED_MESHES[mesh_name]['mpaso_id'],
        omega_id=CACHED_MESHES[mesh_name]['omega_id'],
        min_res=CACHED_MESHES[mesh_name]['min_res'],
        approx_cell_count=CACHED_MESHES[mesh_name]['cell_count'],
    )
    step = _ConfigOnlyStep(config)
    init_condition.add_input_files(cast(OceanModelStep, step))

    by_kind = dict(step.calls)
    assert 'init' in by_kind
    assert by_kind['init']['target'].startswith(f'ocean.{mesh_name}.')
    if model == 'omega':
        # 'teos-10' from config, normalized, has to reach the filename
        assert '.teos10.' in by_kind['init']['target']
        assert 'graph.info' not in by_kind
    else:
        assert by_kind['init']['target'].endswith('.zerovel.nc')
        assert 'graph.info' in by_kind

    # the forcing streams are pointed at whatever holds the wind stress
    assert init_condition.get_forcing_filename(cast(OceanModelStep, step))


def _task_config(mesh_name, model):
    """The config a RealisticGlobalForward on ``mesh_name`` would build."""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'forward.cfg',
    )
    add_realistic_global_mesh_config(config, mesh_name)
    config.set('ocean', 'model', model)
    config.combine()
    return config


def _variant_config(mesh_name, time_integrator):
    """
    The forward options a ``time_integrator`` task on ``mesh_name`` would
    build
    """
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forward',
        'forward.cfg',
    )
    add_realistic_global_mesh_config(config, mesh_name)
    if time_integrator == 'rk4':
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward', 'rk4.cfg'
        )
    config.combine()
    return config


def _stage_for_mesh(mesh_name, time_integrator='split_explicit'):
    """The ForwardStage a task on ``mesh_name`` would build."""
    return ForwardStage.from_config(
        _variant_config(mesh_name, time_integrator)
    )


def _qu240_database_ic():
    """The cached QU.240km initial condition"""
    return DatabaseInitialCondition(
        mesh_name='QU.240km',
        mpaso_id=151209,
        omega_id=260807,
        min_res=240.0,
        approx_cell_count=7153,
    )


def test_realistic_global_forward_without_init_steps():
    """
    The task is the same either way; only where the model inputs come from
    changes.  A source that downloads a cached initial condition brings no
    upstream steps with it, so the task is just the forward run, and its
    directory name keeps it apart from the init-chain task on the same mesh.
    """
    component = Ocean()
    init_condition = _qu240_database_ic()
    task = RealisticGlobalForward(
        component=component,
        mesh_name='QU.240km',
        init_condition=init_condition,
        subdir_name='cached_forward',
    )
    # the forward run and its two diagnostics, and nothing upstream of them
    assert list(task.steps) == ['short', 'global_stats', 'viz']
    assert task.subdir == (
        'spherical/realistic_global/QU.240km/cached_forward/split_explicit/task'
    )
    assert task.steps['short'].init_condition is init_condition
    # the diagnostics are diagnostics, not part of the run
    assert task.steps_to_run == ['short']


def test_forward_task_config_has_the_viz_colormaps():
    """
    Every forward task has a viz step, which reads its colormaps from
    realistic_global.cfg, so the task's config has to include that file.
    """
    init_condition = DatabaseInitialCondition(
        mesh_name='QU.240km',
        mpaso_id=151209,
        omega_id=260807,
        min_res=240.0,
        approx_cell_count=7153,
    )
    task = RealisticGlobalForward(
        component=Ocean(),
        mesh_name='QU.240km',
        init_condition=init_condition,
    )
    config = task.config
    config.combine()
    for field in [
        'temperature',
        'salinity',
        'layerThickness',
        'windStress',
        'kineticEnergyCell',
    ]:
        assert config.has_section(f'realistic_global_viz_{field}')


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
