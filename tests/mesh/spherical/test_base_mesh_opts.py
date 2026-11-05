from polaris.component import Component
from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import QuasiUniformSphericalMeshStep


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
    step.config.set('spherical_mesh', 'jigsaw_optm_qlim', '0.5')

    step.setup()

    assert step.opts.optm_kern == 'cvt+dqdx'
    assert step.opts.optm_iter == 64
    assert step.opts.optm_qtol == 1.0e-6
    assert step.opts.optm_qlim == 0.5
