from polaris.model_step import ModelStep


def _make_step():
    # the method uses no step attributes, so skip the constructor
    return ModelStep.__new__(ModelStep)


def test_floats_keep_full_precision():
    options = {
        'land_ice_fluxes': {
            'config_land_ice_flux_jenkins_salt_transfer_coefficient': (
                0.00055428571
            ),
            'config_land_ice_flux_boundaryLayerThickness': 10.0,
        },
        'eos_linear': {'config_eos_linear_densityref': 1027.51},
        'cvmix': {'config_cvmix_background_diffusion': 5.0e-5},
    }
    namelist = _make_step().map_yaml_to_namelist(options)
    for section in options.values():
        for name, value in section.items():
            assert float(namelist[name]) == value


def test_other_types():
    options = {'section': {'flag': True, 'count': 3, 'name': 'linear'}}
    namelist = _make_step().map_yaml_to_namelist(options)
    assert namelist == {'flag': '.true.', 'count': '3', 'name': "'linear'"}
