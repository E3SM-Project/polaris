from polaris.config import PolarisConfigParser
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean


def _make_step():
    """An Omega forward step with the MPAS-Ocean-to-Omega option map loaded"""
    component = Ocean()
    component.model = 'omega'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )
    config = PolarisConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', 'omega')
    step.config = config
    step._read_config_map()
    return step


def test_submesoscale_options_map_to_the_submeso_section():
    step = _make_step()
    configs = step.map_yaml_configs(
        configs={
            'submesoscale_eddy_parameterization': {
                'config_submesoscale_enable': True,
                'config_submesoscale_tau': 172800.0,
                'config_submesoscale_Ce': 0.08,
                'config_submesoscale_Lfmin': 1.0e3,
                'config_submesoscale_ds_max': 1.0e5,
            }
        },
        config_model='ocean',
    )

    assert configs == {
        'Submeso': {
            'Enable': True,
            'Tau': 172800.0,
            'Ce': 0.08,
            'LfMin': 1.0e3,
            'DsMax': 1.0e5,
        }
    }


def test_submesoscale_variables_map_to_omega_names():
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    mpaso = ['normalMLEvelocity', 'dThreshMLD']
    omega = component.map_var_list_to_native_model(mpaso)
    assert omega == ['EddyVelocity', 'DenMixLayerDepth']
    assert component.map_var_list_from_native_model(omega) == mpaso
