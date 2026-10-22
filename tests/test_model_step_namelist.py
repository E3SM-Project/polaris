from polaris import Component, ModelStep


def test_namelist_floats_keep_full_precision():
    """
    Namelist floats must not be rounded, e.g. a mesh's median cell width,
    which MPAS-Ocean scales horizontal mixing from and which must match the
    median Omega computes
    """
    step = ModelStep(component=Component(name='ocean'), name='forward')
    options = {
        'hmix': {
            'config_hmix_ref_cell_width': 35919.34124270925,
            'config_mom_del4': 2.06e11,
            'config_mom_del2': 1.0e-5,
        }
    }
    namelist = step.map_yaml_to_namelist(options)
    for option, value in options['hmix'].items():
        assert float(namelist[option]) == value
