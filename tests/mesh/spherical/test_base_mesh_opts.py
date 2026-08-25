from polaris.component import Component
from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import QuasiUniformSphericalMeshStep
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.mesh.spherical.unified.configs import get_unified_mesh_config

# the values QuasiUniformSphericalMeshStep hard-coded, or left at jigsaw's
# defaults, before they became config options
PREVIOUS_DEFAULTS = dict(
    jigsaw_optm_kern='odt+dqdx',
    jigsaw_optm_iter=16,
    jigsaw_optm_qtol=1.0e-4,
    jigsaw_optm_qlim=0.9375,
)


def test_shipped_defaults_match_the_previous_hard_coded_values():
    """
    Making these configurable must not change any mesh that has not opted
    into different settings.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')

    assert (
        config.get('spherical_mesh', 'jigsaw_optm_kern')
        == (PREVIOUS_DEFAULTS['jigsaw_optm_kern'])
    )
    assert (
        config.getint('spherical_mesh', 'jigsaw_optm_iter')
        == (PREVIOUS_DEFAULTS['jigsaw_optm_iter'])
    )
    assert (
        config.getfloat('spherical_mesh', 'jigsaw_optm_qtol')
        == (PREVIOUS_DEFAULTS['jigsaw_optm_qtol'])
    )
    assert (
        config.getfloat('spherical_mesh', 'jigsaw_optm_qlim')
        == (PREVIOUS_DEFAULTS['jigsaw_optm_qlim'])
    )


def test_quasi_uniform_step_passes_the_options_to_jigsaw():
    step = QuasiUniformSphericalMeshStep(
        component=Component(name='mesh'),
        subdir='spherical/test/base_mesh',
        cell_width=240.0,
    )
    step.config = PolarisConfigParser()
    step.config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')
    step.config.set('spherical_mesh', 'jigsaw_optm_kern', 'cvt+dqdx')
    step.config.set('spherical_mesh', 'jigsaw_optm_iter', '64')
    step.config.set('spherical_mesh', 'jigsaw_optm_qtol', '1.0e-6')

    step.setup()

    assert step.opts.optm_kern == 'cvt+dqdx'
    assert step.opts.optm_iter == 64
    assert step.opts.optm_qtol == 1.0e-6
    assert step.opts.optm_qlim == PREVIOUS_DEFAULTS['jigsaw_optm_qlim']


def test_unified_meshes_keep_the_default_optimisation_kernel():
    """
    cvt+dqdx was tried for unified meshes and reverted: it thinned the bulk
    of the dcEdge distribution but introduced rare severe defects that the
    diagnostic, being a minimum, is precisely sensitive to.  Guard the
    revert so it is not reintroduced without revisiting the design doc.
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        config = get_unified_mesh_config(mesh_name=mesh_name)

        assert (
            config.get('spherical_mesh', 'jigsaw_optm_kern')
            == (PREVIOUS_DEFAULTS['jigsaw_optm_kern'])
        ), mesh_name
        assert (
            config.getint('spherical_mesh', 'jigsaw_optm_iter')
            == (PREVIOUS_DEFAULTS['jigsaw_optm_iter'])
        ), mesh_name
        assert (
            config.getfloat('spherical_mesh', 'jigsaw_optm_qtol')
            == (PREVIOUS_DEFAULTS['jigsaw_optm_qtol'])
        ), mesh_name
        assert (
            config.getfloat('spherical_mesh', 'jigsaw_optm_qlim')
            == (PREVIOUS_DEFAULTS['jigsaw_optm_qlim'])
        ), mesh_name
