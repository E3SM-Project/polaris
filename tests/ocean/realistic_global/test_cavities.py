import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.cavities import (
    check_cavities_supported,
    copy_antarctic_boundary_convention,
    get_antarctic_boundary_convention,
    has_ice_shelf_cavities,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps import (
    get_realistic_dynamic_adjustment_steps,
)


def _config(convention=None, model='mpas-ocean'):
    config = PolarisConfigParser()
    config.set('ocean', 'model', model)
    if convention is not None:
        config.set(
            'spherical_mesh', 'antarctic_boundary_convention', convention
        )
    return config


def test_convention_defaults_to_the_calving_front():
    config = _config()
    assert get_antarctic_boundary_convention(config) == 'calving_front'
    assert not has_ice_shelf_cavities(config)


@pytest.mark.parametrize(
    'convention, cavities',
    [
        ('calving_front', False),
        ('grounding_line', True),
        ('bedrock_zero', True),
    ],
)
def test_cavities_follow_the_convention(convention, cavities):
    assert has_ice_shelf_cavities(_config(convention)) == cavities


def test_unknown_convention_is_an_error():
    with pytest.raises(ValueError, match='antarctic_boundary_convention'):
        get_antarctic_boundary_convention(_config('ice_front'))


def test_copy_convention():
    config = PolarisConfigParser()
    copy_antarctic_boundary_convention(config, _config('bedrock_zero'))
    assert get_antarctic_boundary_convention(config) == 'bedrock_zero'


@pytest.mark.parametrize('convention', ['grounding_line', 'bedrock_zero'])
def test_cavities_are_mpas_ocean_only(convention):
    check_cavities_supported(_config(convention, model='mpas-ocean'))
    with pytest.raises(ValueError, match='only supported with MPAS-Ocean'):
        check_cavities_supported(_config(convention, model='omega'))


def test_omega_without_cavities_is_supported():
    check_cavities_supported(_config('calving_front', model='omega'))


def test_adjustment_config_carries_the_convention():
    # the dynamic-adjustment config starts from the cull step's convention
    component = Ocean()
    _, config, _ = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='qu240km'
    )
    assert config.get('spherical_mesh', 'antarctic_boundary_convention') == (
        'calving_front'
    )
