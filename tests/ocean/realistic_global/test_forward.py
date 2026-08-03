from configparser import ConfigParser
from types import SimpleNamespace
from typing import cast

import pytest

from polaris import Step
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
    Forward,
    ForwardStage,
    StepInitialCondition,
)
from polaris.yaml import PolarisYaml


def _forward_config(**overrides):
    """A minimal ``[realistic_global_forward]`` config for stage tests."""
    values = dict(
        mpaso_time_integrator='split_explicit_ab2',
        omega_time_integrator='RK4',
        run_duration='0030_00:00:00',
        output_interval='0010_00:00:00',
        restart_interval='',
        dt_per_km='30.0',
        btr_dt_per_km='1.5',
        dt='',
        btr_dt='',
        Rayleigh_damping_coeff='',
        mom_del2='1.0e3',
        mom_del4='1.2e11',
        tracer_del2='',
        tracer_del4='',
        use_Leith_del2='False',
        hmix_scaling='none',
        hmix_ref_cell_width='30.0e3',
        use_GM='True',
        GM_closure='',
        GM_constant_kappa='',
        use_Redi='True',
        use_frazil_ice_formation='False',
        start_time='0001-01-01_00:00:00',
    )
    values.update(overrides)
    config = ConfigParser()
    config.add_section('realistic_global_forward')
    for key, value in values.items():
        config.set('realistic_global_forward', key, value)
    return config


class _FakeStep:
    """Records the input files an InitialCondition adds to a forward step."""

    def __init__(self, model='mpas-ocean', eos_type='teos-10', path='WORK'):
        self.path = path
        self.calls = []
        self.config = ConfigParser()
        self.config.add_section('ocean')
        self.config.set('ocean', 'model', model)
        self.config.set('ocean', 'eos_type', eos_type)

    def add_horiz_mesh_input_file(self, **kwargs):
        self.calls.append(('horiz_mesh', kwargs))

    def add_vert_coord_input_file(self, **kwargs):
        self.calls.append(('vert_coord', kwargs))

    def add_init_input_file(self, **kwargs):
        self.calls.append(('init', kwargs))


# --- ForwardStage ---


def test_from_config_defaults_and_restart_default():
    stage = ForwardStage.from_config(_forward_config())
    assert stage.run_duration == '0030_00:00:00'
    assert stage.output_interval == '0010_00:00:00'
    # a blank restart_interval defaults to run_duration
    assert stage.restart_interval == '0030_00:00:00'
    assert stage.dt is None
    assert stage.btr_dt is None
    assert stage.dt_per_km == 30.0
    assert stage.btr_dt_per_km == 1.5
    assert stage.damping is None
    assert stage.do_restart is False


def test_model_replacements_mpas_ocean_from_per_km():
    stage = ForwardStage.from_config(_forward_config())
    rep = stage.model_replacements('mpas-ocean', min_res=30.0)
    assert rep['dt'] == '0000_00:15:00.000'  # 30 s/km * 30 km = 900 s
    assert rep['btr_dt'] == '0000_00:00:45.000'  # 1.5 s/km * 30 km = 45 s
    assert rep['time_integrator'] == 'split_explicit_ab2'
    assert rep['output_freq'] == '864000'  # 10 days
    assert rep['restart_freq'] == '2592000'  # 30 days (restart == run)
    assert rep['do_restart'] == 'false'
    assert rep['start_time'] == '0001-01-01_00:00:00'


def test_model_replacements_explicit_dt_overrides_per_km():
    stage = ForwardStage.from_config(
        _forward_config(dt='00:10:00', btr_dt='00:00:15')
    )
    rep = stage.model_replacements('mpas-ocean', min_res=999.0)
    assert rep['dt'] == '00:10:00'
    assert rep['btr_dt'] == '00:00:15'


def test_model_replacements_omega_maps_rk4():
    stage = ForwardStage.from_config(_forward_config())
    rep = stage.model_replacements('omega', min_res=30.0)
    assert rep['time_integrator'] == 'RungeKutta4'


def test_the_two_models_get_their_own_integrator_and_time_step():
    # the default is split time stepping for MPAS-Ocean, which Omega does not
    # support yet, and RK4 for Omega; the time step follows from that choice
    stage = ForwardStage.from_config(_forward_config())
    rep = stage.model_replacements('mpas-ocean', min_res=30.0)
    assert rep['time_integrator'] == 'split_explicit_ab2'
    assert rep['dt'] == '0000_00:15:00.000'  # 30 s/km * 30 km
    rep_omega = stage.model_replacements('omega', min_res=30.0)
    assert rep_omega['time_integrator'] == 'RungeKutta4'
    assert rep_omega['dt'] == '0000_00:00:45.000'  # 1.5 s/km * 30 km


def test_non_split_integrators_use_the_short_time_step():
    # RK4 / RungeKutta4 have no barotropic split, so config_dt must be the
    # short barotropic step (btr_dt_per_km), not the long baroclinic dt_per_km
    stage = ForwardStage.from_config(
        _forward_config(mpaso_time_integrator='RK4')
    )
    rep = stage.model_replacements('mpas-ocean', min_res=30.0)
    assert rep['dt'] == '0000_00:00:45.000'  # 1.5 s/km * 30 km, not 30 s/km
    rep_omega = stage.model_replacements('omega', min_res=30.0)
    assert rep_omega['dt'] == '0000_00:00:45.000'


def test_model_replacements_omega_rejects_split_explicit():
    stage = ForwardStage.from_config(
        _forward_config(omega_time_integrator='split_explicit_ab2')
    )
    with pytest.raises(ValueError, match='not supported for Omega'):
        stage.model_replacements('omega', min_res=30.0)
    # the MPAS-Ocean side is unaffected by the unsupported Omega option
    assert stage.model_replacements('mpas-ocean', min_res=30.0)


def test_model_replacements_omega_defers_split_explicit_to_run_time():
    # at setup the integrator may still be changed before running, so an
    # unsupported integrator must not raise; the neutral name is left in place
    stage = ForwardStage.from_config(
        _forward_config(omega_time_integrator='split_explicit_ab2')
    )
    rep = stage.model_replacements('omega', min_res=30.0, at_setup=True)
    assert rep['time_integrator'] == 'split_explicit_ab2'


def test_model_replacements_requires_a_time_step():
    stage = ForwardStage.from_config(_forward_config(dt_per_km=''))
    with pytest.raises(ValueError, match='dt_per_km'):
        stage.model_replacements('mpas-ocean', min_res=30.0)


def test_bottom_drag_options():
    assert ForwardStage().bottom_drag_options() == {}
    options = ForwardStage(damping=1.0e-4).bottom_drag_options()
    assert options == {
        'config_implicit_bottom_drag_type': 'constant_and_rayleigh',
        'config_Rayleigh_damping_coeff': 1.0e-4,
    }


# --- physics options ---


def test_from_config_reads_physics_options():
    stage = ForwardStage.from_config(
        _forward_config(
            mom_del2='462.0',
            tracer_del4='1.2e11',
            use_Leith_del2='True',
            hmix_scaling='scale_with_mesh',
            GM_closure='constant',
            GM_constant_kappa='600.0',
            use_Redi='False',
            use_frazil_ice_formation='True',
        )
    )
    assert stage.mom_del2 == 462.0
    assert stage.tracer_del2 is None
    assert stage.tracer_del4 == 1.2e11
    assert stage.use_Leith_del2
    assert stage.hmix_scaling == 'scale_with_mesh'
    assert stage.GM_closure == 'constant'
    assert stage.GM_constant_kappa == 600.0
    assert stage.use_GM
    assert not stage.use_Redi
    assert stage.use_frazil_ice_formation


def test_from_config_rejects_unknown_hmix_scaling():
    with pytest.raises(ValueError, match='hmix_scaling'):
        ForwardStage.from_config(_forward_config(hmix_scaling='bogus'))


def test_horiz_mixing_options_blank_coefficient_turns_a_term_off():
    """
    A blank coefficient turns its term off explicitly rather than leaving the
    model default, since the MPAS-Ocean Registry defaults are all off and a
    run without horizontal mixing goes unstable.
    """
    options = ForwardStage(
        mom_del2=None, mom_del4=3.2e09
    ).horiz_mixing_options()
    assert options == {
        'config_use_mom_del2': False,
        'config_use_mom_del4': True,
        'config_mom_del4': 3.2e09,
        'config_use_tracer_del2': False,
        'config_use_tracer_del4': False,
    }


def test_horiz_mixing_options_are_all_mapped_to_omega():
    """
    Every option in the neutral bucket must have an Omega counterpart, since
    it is added with ``config_model='ocean'``.  An unmapped option would only
    warn, so the mixing would be silently dropped for Omega.
    """
    step = OceanModelStep.__new__(OceanModelStep)
    step._read_config_map()
    stage = ForwardStage(
        mom_del2=1.0e3, mom_del4=1.2e11, tracer_del2=10.0, tracer_del4=1.2e11
    )
    for option, value in stage.horiz_mixing_options().items():
        # raises ValueError if the option has no Omega counterpart
        step._map_mpaso_to_omega_section_option(option=option, value=value)


def test_forward_yaml_neutral_options_are_all_mapped_to_omega():
    """
    Everything in the ``ocean`` section of ``forward.yaml`` is meant to reach
    both models, so every option there must have an Omega counterpart.  An
    unmapped option would only warn, so it would be silently dropped for Omega
    and the two models would run different physics.
    """
    step = OceanModelStep.__new__(OceanModelStep)
    step._read_config_map()
    stage = ForwardStage.from_config(_forward_config())
    replacements = stage.model_replacements('mpas-ocean', min_res=30.0)
    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=replacements,
        model='ocean',
    )
    for section, options in yaml.configs.items():
        for option, value in options.items():
            # raises ValueError if the option has no Omega counterpart
            step._map_mpaso_to_omega_section_option(
                option=option, value=value, section=section
            )


def test_mpaso_physics_options_hmix_scaling_sets_both_flags():
    """
    Both scaling flags are always set, so that turning scaling off in a user
    config undoes a per-mesh config that turned it on.
    """
    options = ForwardStage(
        hmix_scaling='ref_cell_width'
    ).mpaso_physics_options()
    assert options['config_hmix_use_ref_cell_width']
    assert not options['config_hmix_scaleWithMesh']

    options = ForwardStage(
        hmix_scaling='scale_with_mesh'
    ).mpaso_physics_options()
    assert not options['config_hmix_use_ref_cell_width']
    assert options['config_hmix_scaleWithMesh']

    options = ForwardStage(hmix_scaling='none').mpaso_physics_options()
    assert not options['config_hmix_use_ref_cell_width']
    assert not options['config_hmix_scaleWithMesh']


def test_mpaso_physics_options_reference_width_only_when_it_applies():
    stage = ForwardStage(
        hmix_scaling='ref_cell_width', hmix_ref_cell_width=1e4
    )
    assert stage.mpaso_physics_options()['config_hmix_ref_cell_width'] == 1e4

    stage = ForwardStage(
        hmix_scaling='scale_with_mesh', hmix_ref_cell_width=1e4
    )
    assert 'config_hmix_ref_cell_width' not in stage.mpaso_physics_options()


def test_mpaso_physics_options_gm_settings_only_when_gm_is_on():
    stage = ForwardStage(
        use_GM=True, GM_closure='constant', GM_constant_kappa=600.0
    )
    options = stage.mpaso_physics_options()
    assert options['config_use_GM']
    assert options['config_GM_closure'] == 'constant'
    assert options['config_GM_constant_kappa'] == 600.0

    stage = ForwardStage(
        use_GM=False, GM_closure='constant', GM_constant_kappa=600.0
    )
    options = stage.mpaso_physics_options()
    assert not options['config_use_GM']
    assert 'config_GM_closure' not in options
    assert 'config_GM_constant_kappa' not in options


def test_mpaso_physics_options_rejects_unknown_hmix_scaling():
    with pytest.raises(ValueError, match='hmix_scaling'):
        ForwardStage(hmix_scaling='bogus').mpaso_physics_options()


# --- InitialCondition sources ---


def test_step_initial_condition_wires_inputs_and_graph():
    path = 'ocean/spherical/realistic_global/icos240km/init/initial_state'
    ic = StepInitialCondition(
        cast(Step, _FakeStep(path=path)),
        min_res=240.0,
        approx_cell_count=10417,
    )
    assert ic.graph_target == f'{path}/culled_graph.info'
    assert ic.min_res == 240.0
    assert ic.approx_cell_count == 10417

    forward = _FakeStep()
    ic.add_input_files(cast(OceanModelStep, forward))
    by_kind = dict(forward.calls)
    assert set(by_kind) == {'horiz_mesh', 'vert_coord', 'init'}
    assert by_kind['horiz_mesh']['work_dir_target'] == f'{path}/mesh.nc'
    assert by_kind['vert_coord']['work_dir_target'] == f'{path}/vert_coord.nc'
    assert by_kind['init']['work_dir_target'] == f'{path}/init.nc'


def test_database_initial_condition_mpas_ocean():
    ic = DatabaseInitialCondition(
        mesh_name='QU240km',
        mesh_id=151209,
        min_res=240.0,
        approx_cell_count=10417,
    )
    assert ic.graph_target is None
    assert ic.min_res == 240.0
    assert ic.approx_cell_count == 10417

    step = _FakeStep(model='mpas-ocean', eos_type='teos-10')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    # only the initial condition is pulled from the database for MPAS-Ocean
    assert set(by_kind) == {'init'}
    assert by_kind['init']['target'] == 'ocean.QU240km.151209.teos10.nc'
    assert by_kind['init']['database'] == 'realistic_global/mpas-ocean'


def test_database_initial_condition_omega_also_adds_mesh():
    ic = DatabaseInitialCondition(
        mesh_name='QU240km',
        mesh_id=151209,
        min_res=240.0,
        approx_cell_count=10417,
        eos_type='teos10',
    )
    step = _FakeStep(model='omega')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    assert set(by_kind) == {'init', 'horiz_mesh'}
    target = 'ocean.QU240km.151209.teos10.nc'
    assert by_kind['init']['target'] == target
    assert by_kind['horiz_mesh']['target'] == target
    assert by_kind['horiz_mesh']['database'] == 'realistic_global/omega'


# --- Forward.compute_cell_count ---


def test_compute_cell_count_uses_estimate_before_mesh_exists():
    # before the mesh exists, the initial condition's estimate is used
    fake = SimpleNamespace(
        _mesh_path=lambda: None,
        init_condition=SimpleNamespace(approx_cell_count=10417),
    )
    assert Forward.compute_cell_count(cast(Forward, fake)) == 10417


def test_compute_cell_count_raises_when_estimate_missing():
    fake = SimpleNamespace(
        _mesh_path=lambda: None,
        init_condition=SimpleNamespace(approx_cell_count=None),
    )
    with pytest.raises(ValueError, match='approx_cell_count'):
        Forward.compute_cell_count(cast(Forward, fake))
