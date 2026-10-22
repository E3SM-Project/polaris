import pytest

from polaris.landice.model import MaliModelStep
from polaris.setup import _get_basic_config, _get_component_config
from polaris.tasks.landice import Landice, get_build_albany

DOME_PACKAGE = 'polaris.tasks.landice.dome'


@pytest.fixture
def landice_config(tmp_path, monkeypatch):
    """The landice component's config options, as setup makes them"""
    monkeypatch.setenv('POLARIS_COMPILER', 'gnu')
    monkeypatch.setenv('POLARIS_MPI', 'openmpi')
    monkeypatch.delenv('POLARIS_ALBANY_LINK_LIBS', raising=False)
    basic_config = _get_basic_config(
        config_file=None,
        machine='chrysalis',
        build=None,
        cmake_flags=None,
        debug=None,
        clean_build=None,
        quiet_build=None,
        work_dir=str(tmp_path),
    )
    component = Landice()
    config = _get_component_config(basic_config, component)
    return component, config


def test_landice_has_a_model():
    assert Landice().has_model()


@pytest.mark.parametrize(
    'albany, has_albany, expected',
    [
        ('detect', False, False),
        ('detect', True, True),
        ('True', False, True),
        ('False', True, False),
    ],
)
def test_get_build_albany(
    landice_config, monkeypatch, albany, has_albany, expected
):
    component, config = landice_config
    component.configure(config, steps=[])
    if has_albany:
        monkeypatch.setenv('POLARIS_ALBANY_LINK_LIBS', '-lalbany')
    config.set('build', 'albany', albany, user=True)

    assert get_build_albany(config) is expected


def test_missing_build_is_built(landice_config):
    component, config = landice_config
    step = MaliModelStep(component=component, name='forward')

    component.configure(config, steps=[step])

    assert config.getboolean('build', 'build')
    assert config.get('build', 'branch').endswith('e3sm_submodules/MALI-Dev')


def test_first_order_needs_albany_environment(landice_config):
    component, config = landice_config
    step = _make_fo_step(component)

    with pytest.raises(ValueError, match='--with-albany'):
        component.configure(config, steps=[step])


def test_first_order_with_albany_environment(landice_config, monkeypatch):
    component, config = landice_config
    monkeypatch.setenv('POLARIS_ALBANY_LINK_LIBS', '-lalbany')
    step = _make_fo_step(component)

    component.configure(config, steps=[step])

    assert get_build_albany(config)


def test_first_order_needs_build_with_albany(
    landice_config, tmp_path, monkeypatch
):
    component, config = landice_config
    build_dir = tmp_path / 'landice_build'
    _make_mali_build(build_dir, albany=False)
    config.set('paths', 'component_path', str(build_dir), user=True)
    # the environment's Albany does not help an existing build without it
    monkeypatch.setenv('POLARIS_ALBANY_LINK_LIBS', '-lalbany')
    step = _make_fo_step(component)

    with pytest.raises(ValueError, match='does not have it'):
        component.configure(config, steps=[step])


def test_first_order_with_build_with_albany(landice_config, tmp_path):
    component, config = landice_config
    build_dir = tmp_path / 'landice_build'
    _make_mali_build(build_dir, albany=True)
    config.set('paths', 'component_path', str(build_dir), user=True)
    step = _make_fo_step(component)

    component.configure(config, steps=[step])

    assert not config.getboolean('build', 'build')


def test_shallow_ice_does_not_need_albany(landice_config):
    component, config = landice_config
    step = MaliModelStep(
        component=component, name='forward', velocity_solver='sia'
    )

    component.configure(config, steps=[step])

    assert not step.needs_albany


def test_first_order_needs_albany_input():
    with pytest.raises(ValueError, match='albany_input_package'):
        MaliModelStep(
            component=Landice(), name='forward', velocity_solver='FO'
        )


def test_first_order_step_gets_albany_input():
    step = _make_fo_step(Landice())

    assert step.needs_albany
    inputs = {entry['filename']: entry for entry in step.input_data}
    assert inputs['albany_input.yaml']['package'] == DOME_PACKAGE
    assert inputs['albany_input.yaml']['copy']


def _make_fo_step(component):
    return MaliModelStep(
        component=component,
        name='forward',
        velocity_solver='FO',
        albany_input_package=DOME_PACKAGE,
    )


def _make_mali_build(build_dir, albany):
    """The files of a MALI build that Polaris made"""
    (build_dir / 'default_inputs').mkdir(parents=True)
    (build_dir / 'src').mkdir()
    for filename in [
        'default_inputs/namelist.landice',
        'default_inputs/streams.landice',
        'src/Registry_processed.xml',
        'landice_model',
    ]:
        (build_dir / filename).write_text('\n', encoding='utf-8')
    (build_dir / 'mali_source.txt').write_text(
        f'source: /e3sm\nalbany: {str(albany).lower()}\n', encoding='utf-8'
    )
