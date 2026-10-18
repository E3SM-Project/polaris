from configparser import ConfigParser

import pytest

from polaris.tasks.ocean.isomip_plus.physics import get_physics_replacements
from polaris.yaml import PolarisYaml

# groups of physics.yaml that the COM physics shares with E3SM's
SHARED_GROUPS = [
    'time_integration',
    'advection',
    'wetting_drying',
    'GM_eddy_parameterization',
    'Redi_isopycnal_mixing',
]

# options in other groups of physics.yaml that the COM physics shares
SHARED_OPTIONS = [
    'config_land_ice_flux_attenuation_coefficient',
    'config_land_ice_flux_boundaryLayerThickness',
    'config_use_implicit_top_drag',
    'config_check_ssh_consistency',
]


def _get_config():
    config = ConfigParser()
    config.add_section('isomip_plus')
    config.set('isomip_plus', 'mom_del2_1km', '38.5')
    config.set('isomip_plus', 'mom_del4_1km', '6.83e6')
    return config


def _read_yaml(filename, replacements=None):
    yaml = PolarisYaml.read(
        filename=filename,
        package='polaris.tasks.ocean.isomip_plus',
        replacements=replacements,
        model='mpas-ocean',
    )
    return yaml.configs


@pytest.mark.parametrize(
    'resolution, mom_del2, mom_del4',
    [(1.0, 38.5, 6.83e6), (2.0, 77.0, 5.464e7), (4.0, 154.0, 4.3712e8)],
)
def test_viscosity_scales_with_resolution(resolution, mom_del2, mom_del4):
    replacements = get_physics_replacements(_get_config(), resolution)
    assert replacements['mom_del2'] == pytest.approx(mom_del2)
    assert replacements['mom_del4'] == pytest.approx(mom_del4)


def test_com_restores_every_e3sm_option():
    # a com variant must not inherit any of E3SM's physics
    replacements = get_physics_replacements(_get_config(), 4.0)
    e3sm = _read_yaml('physics.yaml', replacements)
    com = _read_yaml('com.yaml')
    for group, options in e3sm.items():
        if group in SHARED_GROUPS:
            assert group not in com
            continue
        for option in options:
            if option in SHARED_OPTIONS:
                assert option not in com.get(group, {})
            else:
                assert option in com[group], option
