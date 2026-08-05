from polaris import Component
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine import get_lat_lon_topo_steps

FILEPATH = 'component/some/where/thing.cfg'


def test_get_or_create_shared_config_creates_and_registers():
    component = Component(name='component')
    config = component.get_or_create_shared_config(filepath=FILEPATH)
    assert config.filepath == FILEPATH
    # registered right away, which is what lets a second caller find it
    assert component.configs[FILEPATH] is config


def test_get_or_create_shared_config_returns_the_same_config():
    component = Component(name='component')
    first = component.get_or_create_shared_config(filepath=FILEPATH)
    second = component.get_or_create_shared_config(filepath=FILEPATH)
    assert second is first


def test_get_or_create_shared_config_sets_up_only_once():
    """
    The setup callback must not run again for an existing config, or a second
    caller would re-add its packages on top of options the first caller's
    steps may already have been given.
    """
    component = Component(name='component')
    calls = []

    def setup(config):
        calls.append(config)
        config.set('section', 'option', 'value')

    first = component.get_or_create_shared_config(
        filepath=FILEPATH, setup=setup
    )
    first.set('section', 'option', 'changed')
    second = component.get_or_create_shared_config(
        filepath=FILEPATH, setup=setup
    )
    assert len(calls) == 1
    assert second.get('section', 'option') == 'changed'


def test_shared_topo_steps_hand_back_the_config_their_steps_use():
    """
    A get_*_steps() helper is called once per consumer.  Building its config
    unconditionally handed the second caller a config that the shared steps --
    created on the first call -- were not using, so options set on it reached
    nothing, and registering it raised.
    """
    first_steps, first_config = get_lat_lon_topo_steps(
        component=e3sm_init, resolution=0.25
    )
    second_steps, second_config = get_lat_lon_topo_steps(
        component=e3sm_init, resolution=0.25
    )
    assert second_config is first_config
    for name, step in first_steps.items():
        assert second_steps[name] is step, name
    # and re-registering what was handed back is a no-op rather than an error
    e3sm_init.add_config(second_config)
