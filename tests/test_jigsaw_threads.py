"""
Tests that JIGSAW is told how many threads to use.

JIGSAW takes its thread count from `NUMTHREAD` in its own job-config file
rather than from `OMP_NUM_THREADS`, so nothing in the environment reaches it.
Left unset it sizes itself from whatever cores it can see -- and the mesh it
produces depends on that count, so the same step built different meshes on
machines with different core counts, and a different one again when confined
to part of an allocation.
"""

import pytest

from polaris import Component
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)


def _step(cls, **kwargs):
    return cls(component=Component(name='mesh'), cell_width=240.0, **kwargs)


@pytest.mark.parametrize(
    'cls', [IcosahedralMeshStep, QuasiUniformSphericalMeshStep]
)
def test_a_mesh_step_declares_the_cores_jigsaw_can_use(cls):
    """
    Measured on Chrysalis, JIGSAW stops improving at about 16 threads from
    60 km down, and returns 2-2.8x however many it is given.  Asking for
    more would reserve cores no mesh can use.
    """
    step = _step(cls)

    assert step.cpus_per_task == 16
    # one core is slower but never blocked, so a mesh always fits
    assert step.min_cpus_per_task == 1


@pytest.mark.parametrize('assigned', [1, 4, 16])
def test_jigsaw_is_told_what_the_step_was_actually_given(assigned):
    """
    The number has to be what the step got, not what it asked for, or the
    serial and concurrent paths would disagree and build different meshes.
    """
    step = _step(QuasiUniformSphericalMeshStep)
    # as constrain_resources() leaves it, before runtime_setup() runs
    step.cpus_per_task = assigned
    for name in ('mesh_file', 'geom_file', 'jcfg_file', 'hfun_file'):
        setattr(step.opts, name, None)
    step.work_path = lambda name: name

    step.runtime_setup()

    assert step.opts.numthread == assigned


def test_jigsaw_is_not_left_to_choose_for_itself():
    """What the default was, and what made a mesh machine-dependent."""
    step = _step(QuasiUniformSphericalMeshStep)

    assert step.opts.numthread is None, (
        'jigsawpy should default to saying nothing; this test is about '
        'polaris filling it in'
    )
