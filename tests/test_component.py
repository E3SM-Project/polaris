import pytest

from polaris import Component
from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine import get_lat_lon_topo_steps
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.forcing.jra55.steps import (
    get_jra55_steps,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
)

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


def test_get_or_create_shared_config_builds_only_once():
    """
    The create callback must not run again for an existing config, or a second
    caller would rebuild on top of options the first caller's steps may already
    have been given.
    """
    component = Component(name='component')
    calls = []

    def create():
        config = PolarisConfigParser(filepath=FILEPATH)
        config.set('section', 'option', 'value')
        calls.append(config)
        return config

    first = component.get_or_create_shared_config(
        filepath=FILEPATH, create=create
    )
    first.set('section', 'option', 'changed')
    second = component.get_or_create_shared_config(
        filepath=FILEPATH, create=create
    )
    assert len(calls) == 1
    assert second is first
    assert second.get('section', 'option') == 'changed'


def test_get_or_create_shared_config_rejects_a_mismatched_filepath():
    """
    A builder that ignores the filepath would register a config under a path it
    does not know about, which is the same silent mismatch this method exists
    to prevent.
    """
    component = Component(name='component')
    with pytest.raises(ValueError, match='filepath'):
        component.get_or_create_shared_config(
            filepath=FILEPATH,
            create=lambda: PolarisConfigParser(filepath='somewhere/else.cfg'),
        )
    assert FILEPATH not in component.configs


@pytest.mark.parametrize(
    'get_steps', [get_woa23_steps, get_jra55_steps], ids=['woa23', 'jra55']
)
def test_shared_steps_hand_back_the_config_their_steps_use(get_steps):
    """
    The two realistic_global helpers that were rebuilding their config, rather
    than getting the one their shared steps are already using.
    """
    component = Ocean()
    first_steps, first_config = get_steps(component=component)
    second_steps, second_config = get_steps(component=component)
    assert second_config is first_config
    for name, step in first_steps.items():
        assert second_steps[name] is step, name
    # and re-registering what was handed back is a no-op rather than an error
    component.add_config(second_config)


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
