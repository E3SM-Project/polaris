import importlib.resources as imp_res
from configparser import ConfigParser
from types import SimpleNamespace
from typing import Any, cast

import pytest
from ruamel.yaml import YAML

from polaris import Step
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
    Forward,
    ForwardStage,
    StatsAnalysis,
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
        stats_interval='0001_00:00:00',
        dt_per_km='30.0',
        btr_dt_per_km='1.5',
        dt='',
        btr_dt='',
        damping='',
        mom_del2='1.0e3',
        mom_del4='1.2e11',
        mom_del4_div_factor='',
        tracer_del2='',
        tracer_del4='',
        use_Leith_del2='False',
        hmix_scaling='none',
        hmix_ref_cell_width='30.0e3',
        use_GM='True',
        GM_closure='',
        GM_constant_kappa='',
        use_Redi='True',
        use_KPP='True',
        use_submesoscale='True',
        pressure_gradient_type='Jacobian_from_TS',
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

    def __init__(
        self,
        model='mpas-ocean',
        eos_type='teos-10',
        path='WORK',
        forcing_filename='forcing.nc',
        init_filename='init.nc',
    ):
        self.path = path
        self.calls = []
        # a real Forward carries the ForwardStage it runs; None means a plain
        # forward run, which always reads the initial state
        self.stage = None
        self.forcing_filename = forcing_filename
        self.init_filename = init_filename
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

    def add_forcing_input_file(self, **kwargs):
        self.calls.append(('forcing', kwargs))

    def add_input_file(self, **kwargs):
        self.calls.append((kwargs.get('filename'), kwargs))

    def get_forcing_filename(self):
        return self.forcing_filename

    def get_init_filename(self):
        return self.init_filename


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


def test_stats_interval_is_independent_of_the_output_interval():
    """
    The statistics are scalars, so they are written far more often than the 3-D
    output; the two cadences must not be tied together.
    """
    stage = ForwardStage.from_config(
        _forward_config(
            output_interval='0010_00:00:00', stats_interval='0000_01:00:00'
        )
    )
    assert stage.output_interval == '0010_00:00:00'
    assert stage.stats_interval == '0000_01:00:00'
    rep = stage.model_replacements('mpas-ocean', min_res=30.0)
    assert rep['stats_interval'] == '0000_01:00:00'
    assert rep['output_interval'] == '0010_00:00:00'
    assert rep['stats_freq'] == '3600'


@pytest.mark.parametrize(
    'stats_interval, expected',
    [
        ('0001_00:00:00', '1Day'),
        ('0002_00:00:00', '2Day'),
        ('0000_06:00:00', '6Hour'),
        ('0000_00:30:00', '30Minute'),
        ('0000_00:00:45', '45Second'),
        # 1 day 12 hours has no whole-day form, so it falls back to hours
        ('0001_12:00:00', '36Hour'),
    ],
)
def test_omega_stats_period_follows_the_stats_interval(
    stats_interval, expected
):
    """
    Omega spells the GlobalStats cadence as a period string rather than an
    interval, so stats_interval has to be translated.  It is the same knob for
    both models; it must not silently apply to MPAS-Ocean alone.
    """
    stage = ForwardStage.from_config(
        _forward_config(stats_interval=stats_interval)
    )
    assert stage.stats_period() == expected
    rep = stage.model_replacements('omega', min_res=30.0)
    assert rep['stats_period'] == expected


def test_omega_global_stats_are_snapshots_not_reductions():
    """
    Omega names a temporal reduction ``<stem>_TimeMean<period>`` and an
    instantaneous sample plain ``<stem>``.  mpaso_to_omega.yaml maps the plain
    names, so the analysis group has to be configured for snapshots or the
    mapped variables will not exist in the output.
    """
    stage = ForwardStage.from_config(_forward_config())
    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=stage.model_replacements('omega', min_res=30.0),
        model='Omega',
    )
    global_stats = yaml.configs['Analysis']['GlobalStats']
    assert global_stats['ReductionPeriod'] == []
    assert global_stats['SnapshotPeriod'] == ['1Day']

    var_map = YAML(typ='rt').load(
        imp_res.files('polaris.ocean.model')
        .joinpath('mpaso_to_omega.yaml')
        .read_text()
    )['variables']
    # the mapped names are the plain (snapshot) form
    assert var_map['temperatureMax'] == 'Temperature_SpatialMax'
    assert not any(
        str(omega_name).startswith('Temperature_SpatialMax_TimeMean')
        for omega_name in var_map.values()
    )


def test_bottom_drag_options():
    # an undamped stage states a zero coefficient rather than leaving the
    # Registry default of 1.0e-4, which reads as though the run were damped
    assert ForwardStage().bottom_drag_options() == {
        'config_Rayleigh_damping_coeff': 0.0,
    }
    options = ForwardStage(damping=1.0e-4).bottom_drag_options()
    assert options == {
        'config_implicit_bottom_drag_type': 'constant_and_rayleigh',
        'config_Rayleigh_damping_coeff': 1.0e-4,
    }


def test_damping_is_an_error_for_omega():
    # Omega has no Rayleigh damping, so a damped stage cannot run there
    stage = ForwardStage(name='damped_adjustment_1', damping=1.0e-4)
    with pytest.raises(ValueError, match='Omega/issues/495'):
        stage.check_damping_supported('omega')
    # ... but it is fine for MPAS-Ocean
    stage.check_damping_supported('mpas-ocean')


def test_no_damping_is_fine_for_either_model():
    # an undamped stage -- the final `simulation` stage, and every stage of a
    # simple forward run -- is unaffected
    for model in ('mpas-ocean', 'omega'):
        ForwardStage(name='simulation').check_damping_supported(model)


# --- physics options ---


def test_from_config_reads_physics_options():
    stage = ForwardStage.from_config(
        _forward_config(
            mom_del2='462.0',
            tracer_del4='1.2e11',
            use_Leith_del2='True',
            hmix_scaling='ref_cell_width',
            mom_del4_div_factor='10.0',
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
    assert stage.hmix_scaling == 'ref_cell_width'
    assert stage.mom_del4_div_factor == 10.0
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


def test_ref_cell_width_scaling_turns_on_both_mpaso_flags():
    """
    MPAS-Ocean reads ``config_hmix_use_ref_cell_width`` only inside
    ``if (config_hmix_scaleWithMesh)``, so setting the first without the second
    reads as a request for width-based scaling and gets none at all.
    """
    options = ForwardStage(
        hmix_scaling='ref_cell_width'
    ).mpaso_physics_options()
    assert options['config_hmix_scaleWithMesh']
    assert options['config_hmix_use_ref_cell_width']


def test_hmix_scaling_none_turns_off_both_mpaso_flags():
    # both flags every time, so that turning scaling off in a user config
    # undoes a per-mesh config that turned it on
    options = ForwardStage(hmix_scaling='none').mpaso_physics_options()
    assert not options['config_hmix_scaleWithMesh']
    assert not options['config_hmix_use_ref_cell_width']


def test_mpaso_physics_options_reference_width_only_when_it_applies():
    stage = ForwardStage(
        hmix_scaling='ref_cell_width', hmix_ref_cell_width=1e4
    )
    assert stage.mpaso_physics_options()['config_hmix_ref_cell_width'] == 1e4

    stage = ForwardStage(hmix_scaling='none', hmix_ref_cell_width=1e4)
    assert 'config_hmix_ref_cell_width' not in stage.mpaso_physics_options()


def test_mpaso_physics_options_del4_div_factor_only_when_set():
    stage = ForwardStage(mom_del4=3.2e09, mom_del4_div_factor=10.0)
    assert stage.mpaso_physics_options()['config_mom_del4_div_factor'] == 10.0

    # blank leaves the model default of 1.0 rather than restating it
    stage = ForwardStage(mom_del4=3.2e09)
    assert 'config_mom_del4_div_factor' not in stage.mpaso_physics_options()

    # MPAS-Ocean only: Omega has no equivalent, so it must not ride in the
    # neutral bucket, which is added with config_model='ocean'
    assert 'config_mom_del4_div_factor' not in stage.horiz_mixing_options()


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


def test_mpaso_only_physics_is_always_stated():
    """
    The KPP boundary layer and the submesoscale parameterization are stated
    either way rather than only when on, so that turning them off in a user or
    per-mesh config undoes a default that turned them on.  The pressure
    gradient is the exception: a blank value means "leave the model default".
    """
    on = ForwardStage(
        use_KPP=True,
        use_submesoscale=True,
        pressure_gradient_type='Jacobian_from_TS',
    ).mpaso_physics_options()
    assert on['config_use_cvmix_kpp']
    assert on['config_submesoscale_enable']
    assert on['config_pressure_gradient_type'] == 'Jacobian_from_TS'

    off = ForwardStage().mpaso_physics_options()
    assert off['config_use_cvmix_kpp'] is False
    assert off['config_submesoscale_enable'] is False
    assert 'config_pressure_gradient_type' not in off


def test_mpaso_physics_options_rejects_unknown_hmix_scaling():
    with pytest.raises(ValueError, match='hmix_scaling'):
        ForwardStage(hmix_scaling='bogus').mpaso_physics_options()


# --- InitialCondition sources ---


def test_step_initial_condition_wires_inputs_and_graph():
    base = 'ocean/spherical/realistic_global/icos240km/init'
    path = f'{base}/initial_state'
    ic = StepInitialCondition(
        cast(Step, _FakeStep(path=path)),
        min_res=240.0,
        approx_cell_count=10417,
        forcing_step=cast(Step, _FakeStep(path=f'{base}/forcing')),
    )
    assert ic.graph_target == f'{path}/culled_graph.info'
    assert ic.min_res == 240.0
    assert ic.approx_cell_count == 10417

    forward = _FakeStep()
    ic.add_input_files(cast(OceanModelStep, forward))
    by_kind = dict(forward.calls)
    assert set(by_kind) == {'horiz_mesh', 'vert_coord', 'init', 'forcing'}
    assert by_kind['horiz_mesh']['work_dir_target'] == f'{path}/mesh.nc'
    assert by_kind['vert_coord']['work_dir_target'] == f'{path}/vert_coord.nc'
    assert by_kind['init']['work_dir_target'] == f'{path}/init.nc'


def test_step_initial_condition_skips_init_on_a_restart():
    """
    A restarting stage reads the restart, not the initial state, so linking
    init.nc would only misrepresent where its state came from.
    """
    base = 'ocean/spherical/realistic_global/icos240km/init'
    ic = StepInitialCondition(
        cast(Step, _FakeStep(path=f'{base}/initial_state')),
        min_res=240.0,
        approx_cell_count=10417,
        forcing_step=cast(Step, _FakeStep(path=f'{base}/forcing')),
    )

    restarting = _FakeStep()
    restarting.stage = ForwardStage(
        name='damped_adjustment_2', do_restart=True
    )
    ic.add_input_files(cast(OceanModelStep, restarting))
    kinds = {kind for kind, _ in restarting.calls}
    assert 'init' not in kinds
    # the mesh is read either way, and so is the forcing
    assert {'horiz_mesh', 'vert_coord', 'forcing'} <= kinds

    first = _FakeStep()
    first.stage = ForwardStage(name='damped_adjustment_1', do_restart=False)
    ic.add_input_files(cast(OceanModelStep, first))
    assert 'init' in {kind for kind, _ in first.calls}


def test_step_initial_condition_requires_a_forcing_step():
    """
    Every realistic_global forward run is wind-forced, so there is no way to
    build a step-based initial condition without a forcing step.
    """
    base = 'ocean/spherical/realistic_global/icos240km/init'
    with pytest.raises(TypeError):
        StepInitialCondition(  # type: ignore[call-arg]
            cast(Step, _FakeStep(path=f'{base}/initial_state')),
            min_res=240.0,
            approx_cell_count=10417,
        )


def test_step_initial_condition_wires_the_forcing_file():
    base = 'ocean/spherical/realistic_global/icos240km/init'
    ic = StepInitialCondition(
        cast(Step, _FakeStep(path=f'{base}/initial_state')),
        min_res=240.0,
        approx_cell_count=10417,
        forcing_step=cast(Step, _FakeStep(path=f'{base}/forcing')),
    )
    assert ic.provides_forcing_file

    forward = _FakeStep(forcing_filename='custom_forcing.nc')
    ic.add_input_files(cast(OceanModelStep, forward))
    by_kind = dict(forward.calls)
    # the staged filename comes from [ocean_staged_files], not a literal
    assert (
        by_kind['forcing']['work_dir_target']
        == f'{base}/forcing/custom_forcing.nc'
    )


def test_forcing_yaml_neutral_options_are_all_mapped_to_omega():
    """
    As for ``forward.yaml``: everything in the ``ocean`` section of
    ``forcing.yaml`` has to reach both models, and an unmapped option would
    only warn, leaving the forcing silently off for Omega.
    """
    step = OceanModelStep.__new__(OceanModelStep)
    step._read_config_map()
    yaml = PolarisYaml.read(
        filename='forcing.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=None,
        model='ocean',
    )
    assert yaml.configs['forcing']['config_use_bulk_wind_stress'] is True
    for section, options in yaml.configs.items():
        for option, value in options.items():
            # raises ValueError if the option has no Omega counterpart
            step._map_mpaso_to_omega_section_option(
                option=option, value=value, section=section
            )


@pytest.mark.parametrize(
    'model, streams_section, stream_name, filename_option',
    [
        ('mpas-ocean', 'streams', 'forcing', 'filename_template'),
        ('Omega', 'IOStreams', 'Forcing', 'Filename'),
    ],
)
def test_forcing_streams_yaml_points_at_the_staged_file(
    model, streams_section, stream_name, filename_option
):
    """
    Each model reads the forcing from a stream of its own, and both must be
    pointed at the configured staged filename rather than the model default
    (``forcing_data.nc`` for MPAS-Ocean).
    """
    yaml = PolarisYaml.read(
        filename='forcing_streams.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=dict(forcing_filename='custom_forcing.nc'),
        model=model,
        streams_section=streams_section,
    )
    stream = yaml.streams[stream_name]
    assert stream[filename_option] == 'custom_forcing.nc'


def test_omega_forcing_stream_is_actually_read():
    """
    Omega's Default.yml gives the Forcing stream ``FreqUnits: Never``, which
    does not mean "read on demand": ``IOStream::create`` returns early for
    'never' and never registers the stream, and ``Forcing`` then falls back to
    zero forcing with only an info-level log line.  The run completes, looks
    fine, and is unforced.

    Every realistic_global forward run is wind-forced, so this must not be
    inherited.  ``OnStartup`` registers the stream and reads it before the
    first step.
    """
    yaml = PolarisYaml.read(
        filename='forcing_streams.yaml',
        package='polaris.tasks.ocean.realistic_global.forward',
        replacements=dict(forcing_filename='forcing.nc'),
        model='Omega',
        streams_section='IOStreams',
    )
    freq_units = yaml.streams['Forcing']['FreqUnits']
    assert freq_units.lower() != 'never', (
        'FreqUnits: Never makes Omega skip the Forcing stream and run unforced'
    )
    assert freq_units == 'OnStartup'


def _database_ic(**overrides) -> DatabaseInitialCondition:
    values: dict[str, Any] = dict(
        mesh_name='QU.240km',
        mpaso_id=151209,
        omega_id=260807,
        min_res=240.0,
        approx_cell_count=7153,
    )
    values.update(overrides)
    return DatabaseInitialCondition(**values)


def test_database_initial_condition_mpas_ocean():
    """
    One zerovel file supplies both the mesh and the initial state, and the
    graph comes from the database beside it rather than from an upstream step.
    """
    ic = _database_ic()
    assert ic.graph_target is None
    assert ic.min_res == 240.0
    assert ic.approx_cell_count == 7153

    step = _FakeStep(model='mpas-ocean', eos_type='teos-10')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    assert set(by_kind) == {'init', 'horiz_mesh', 'graph.info'}
    database = 'realistic_global/mpas-ocean/QU.240km'
    target = 'ocean.QU.240km.151209.zerovel.nc'
    for kind in ('init', 'horiz_mesh'):
        assert by_kind[kind]['target'] == target
        assert by_kind[kind]['database'] == database
    assert by_kind['graph.info']['target'] == 'graph.info.151209'
    assert by_kind['graph.info']['database'] == database


def test_database_initial_condition_omega():
    """
    Omega reads one file as mesh, vertical coordinate and initial state, and
    partitions internally, so it needs no graph.
    """
    ic = _database_ic()
    step = _FakeStep(model='omega', eos_type='teos-10')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    assert set(by_kind) == {'init', 'horiz_mesh', 'vert_coord'}
    # 'teos-10' from config is normalized to the 'teos10' in the filename
    target = 'ocean.QU.240km.151209.teos10.260807.nc'
    for kind in ('init', 'horiz_mesh', 'vert_coord'):
        assert by_kind[kind]['target'] == target
        assert by_kind[kind]['database'] == 'realistic_global/omega/QU.240km'


def test_database_initial_condition_needs_an_omega_id_for_omega():
    """
    The Omega filename carries a second id.  Without it the name would be
    silently wrong, and the failure would be a download error far from the
    cause.
    """
    ic = _database_ic(omega_id=None)
    step = _FakeStep(model='omega')
    with pytest.raises(ValueError, match='omega_id'):
        ic.add_input_files(cast(OceanModelStep, step))
    # MPAS-Ocean does not need it
    ic.add_input_files(cast(OceanModelStep, _FakeStep(model='mpas-ocean')))


def test_database_forcing_streams_read_the_initial_condition():
    """
    Every realistic_global forward run is wind-forced.  A database source
    carries the wind stress inside the initial-condition file, so the forcing
    streams have to be pointed at that file rather than at a forcing file that
    does not exist.
    """
    ic = _database_ic()
    assert ic.provides_forcing_file
    step = _FakeStep(model='mpas-ocean', init_filename='init.nc')
    assert ic.get_forcing_filename(cast(OceanModelStep, step)) == 'init.nc'
    # a step-backed source keeps using its own staged forcing file
    step_ic = StepInitialCondition(
        cast(Step, _FakeStep(path='WORK/initial_state')),
        min_res=240.0,
        approx_cell_count=7153,
        forcing_step=cast(Step, _FakeStep(path='WORK/forcing')),
    )
    assert (
        step_ic.get_forcing_filename(cast(OceanModelStep, step))
        == 'forcing.nc'
    )


# --- StatsAnalysis ---


class _FakeForwardStep:
    """Stands in for the forward step StatsAnalysis reads from."""

    def __init__(self, path='WORK/short', stage=None):
        self.path = path
        self.stage = stage


class _RecordingStatsAnalysis(StatsAnalysis):
    """A StatsAnalysis that records what setup() adds instead of resolving
    real paths."""

    def __init__(self, component, forward_step, config):
        self.added: list = []
        super().__init__(
            component=component, indir='WORK', forward_step=forward_step
        )
        self.config = config

    def add_input_file(self, **kwargs: Any):  # type: ignore[override]
        self.added.append(kwargs)

    def add_output_file(self, *args, **kwargs):
        pass


def _stats_step(model, stage=None, stats_interval='0001_00:00:00'):
    component = Ocean()
    component.model = model
    component._read_variables_yaml()
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    forward_config = _forward_config(stats_interval=stats_interval)
    config.add_section('realistic_global_forward')
    for option, value in forward_config.items('realistic_global_forward'):
        config.set('realistic_global_forward', option, value)
    step = _RecordingStatsAnalysis(
        component=component,
        forward_step=_FakeForwardStep(stage=stage),
        config=cast(Any, config),
    )
    return step, step.added


@pytest.mark.parametrize(
    'stats_interval, expected',
    [
        ('0001_00:00:00', 'WORK/short/global_stats_1DayInstants'),
        ('0000_06:00:00', 'WORK/short/global_stats_6HourInstants'),
    ],
)
def test_stats_analysis_reads_omegas_instants_file(stats_interval, expected):
    """
    Omega builds the real filename from the configured prefix, the analysis
    period and the kind of output.  The forward runs ask for instantaneous
    samples, so the file is ``<prefix>_<period>Instants`` -- not the
    ``TimeStats`` name a temporal reduction would write, which is what this
    step looked for while nothing configured a reduction.
    """
    step, added = _stats_step('omega', stats_interval=stats_interval)
    step.setup()
    assert [entry['work_dir_target'] for entry in added] == [expected]


def test_stats_analysis_reads_mpas_oceans_plain_file():
    """MPAS-Ocean writes the configured filename as given."""
    step, added = _stats_step('mpas-ocean')
    step.setup()
    assert [entry['work_dir_target'] for entry in added] == [
        'WORK/short/global_stats.nc'
    ]


def test_stats_analysis_prefers_the_forward_steps_stage():
    """
    A stage carried by the forward step wins over the config, so that a
    multi-stage workflow whose stages differ finds each one's own file.
    """
    stage = ForwardStage.from_config(
        _forward_config(stats_interval='0000_00:30:00')
    )
    step, added = _stats_step(
        'omega', stage=stage, stats_interval='0001_00:00:00'
    )
    step.setup()
    assert [entry['work_dir_target'] for entry in added] == [
        'WORK/short/global_stats_30MinuteInstants'
    ]


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


# --- restart chaining ---


def test_restart_stream_replacements_switch_omegas_read_side():
    """
    MPAS-Ocean's restart stream is both input and output, so it needs nothing
    here; Omega reads through a separate RestartRead that has to be switched
    off for a stage that is not restarting.
    """
    first = ForwardStage(name='first').restart_stream_replacements()
    # the first stage reads InitialState, and RestartRead never opens
    assert first['init_freq_units'] == 'OnStartup'
    assert first['restart_read_use_start_end'] == 'true'
    assert first['restart_read_time'] == '99999-12-31_00:00:00'

    second = ForwardStage(
        name='second',
        do_restart=True,
        start_time='0001-01-11_00:00:00',
    ).restart_stream_replacements()
    assert second['init_freq_units'] == 'never'
    assert second['restart_read_use_start_end'] == 'false'
    assert second['restart_read_time'] == '0001-01-11_00:00:00'


def test_restart_streams_yaml_requests_omegas_restart_read():
    """
    Setup drops any Default.yml stream no yaml file asks for, and forward.yaml
    requests only RestartWrite and History, so RestartRead has to be asked for
    here or an Omega stage could not read its predecessor's restart.
    """
    text = (
        imp_res.files('polaris.tasks.ocean.realistic_global.forward')
        .joinpath('restart_streams.yaml')
        .read_text()
    )
    streams = YAML(typ='rt').load(
        text.replace('{{ init_freq_units }}', 'never')
        .replace('{{ restart_read_use_start_end }}', 'false')
        .replace('{{ restart_read_time }}', '0001-01-11_00:00:00')
    )
    omega = streams['Omega']['IOStreams']
    assert set(omega) == {'InitialState', 'RestartRead', 'RestartWrite'}
    assert omega['RestartRead']['UsePointerFile'] is False
    # both directions point at the shared restarts directory
    for name in ('RestartRead', 'RestartWrite'):
        assert omega[name]['Filename'] == '../restarts/rst.$Y-$M-$D_$h.$m.$s'

    restart = streams['mpas-ocean']['streams']['restart']
    assert restart['filename_template'] == (
        '../restarts/rst.$Y-$M-$D_$h.$m.$s.nc'
    )
    # the restart is read once, at initialization, not on a cadence
    assert restart['input_interval'] == 'initial_only'
