from configparser import ConfigParser

import pytest

from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean


def _make_step(model):
    component = Ocean()
    component.model = model
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )
    return step


def _make_config(
    model,
    eos_type,
    with_linear_options=True,
    tref=0.0,
    sref=0.0,
):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.set('ocean', 'eos_type', eos_type)
    if with_linear_options:
        config.set('ocean', 'eos_linear_alpha', '0.2')
        config.set('ocean', 'eos_linear_beta', '0.8')
        config.set('ocean', 'eos_linear_rhoref', '973.0')
        config.set('ocean', 'eos_linear_Tref', str(tref))
        config.set('ocean', 'eos_linear_Sref', str(sref))
    return config


def _get_eos_options(step):
    """Get the options passed to add_model_config_options"""
    assert len(step.model_config_data) == 1
    entry = step.model_config_data[0]
    assert entry['config_model'] == 'ocean'
    return entry['options']


def test_linear_mpas_ocean():
    step = _make_step(model='mpas-ocean')
    step.config = _make_config(
        model='mpas-ocean', eos_type='linear', tref=5.0, sref=35.0
    )
    step.update_namelist_eos()
    options = _get_eos_options(step)
    assert options == {
        'config_eos_type': 'linear',
        'config_eos_linear_alpha': 0.2,
        'config_eos_linear_beta': 0.8,
        'config_eos_linear_densityref': 973.0,
        'config_eos_linear_Tref': 5.0,
        'config_eos_linear_Sref': 35.0,
    }


def test_linear_omega():
    step = _make_step(model='omega')
    step.config = _make_config(model='omega', eos_type='linear')
    step.update_namelist_eos()
    options = _get_eos_options(step)
    assert options == {
        'config_eos_type': 'linear',
        'config_eos_linear_alpha': 0.2,
        'config_eos_linear_beta': 0.8,
        'config_eos_linear_densityref': 973.0,
    }


@pytest.mark.parametrize('tref,sref', [(5.0, 0.0), (0.0, 35.0)])
def test_linear_omega_nonzero_ref_raises(tref, sref):
    step = _make_step(model='omega')
    step.config = _make_config(
        model='omega', eos_type='linear', tref=tref, sref=sref
    )
    with pytest.raises(ValueError, match='Nonzero Tref and Sref'):
        step.update_namelist_eos()


def test_constant_mpas_ocean():
    step = _make_step(model='mpas-ocean')
    step.config = _make_config(model='mpas-ocean', eos_type='constant')
    step.update_namelist_eos()
    options = _get_eos_options(step)
    # MPAS-Ocean has no constant EOS so it maps to linear
    assert options['config_eos_type'] == 'linear'


def test_constant_omega():
    step = _make_step(model='omega')
    step.config = _make_config(model='omega', eos_type='constant')
    step.update_namelist_eos()
    options = _get_eos_options(step)
    assert options['config_eos_type'] == 'constant'


def test_teos10_mpas_ocean():
    step = _make_step(model='mpas-ocean')
    # teos10.cfg does not define the eos_linear_* options, so they must
    # not be read
    step.config = _make_config(
        model='mpas-ocean', eos_type='teos-10', with_linear_options=False
    )
    step.update_namelist_eos()
    options = _get_eos_options(step)
    # MPAS-Ocean has no TEOS-10 option so it maps to Jackett-McDougall
    assert options == {'config_eos_type': 'jm'}


def test_teos10_omega():
    step = _make_step(model='omega')
    step.config = _make_config(
        model='omega', eos_type='teos-10', with_linear_options=False
    )
    step.update_namelist_eos()
    options = _get_eos_options(step)
    assert options == {'config_eos_type': 'teos-10'}


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_unsupported_eos_type_raises(model):
    step = _make_step(model=model)
    step.config = _make_config(
        model=model, eos_type='wright', with_linear_options=False
    )
    with pytest.raises(ValueError, match='Unsupported equation of state'):
        step.update_namelist_eos()
