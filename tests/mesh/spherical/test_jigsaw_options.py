"""
Tests that a JIGSAW mesh step can be made without JIGSAW-Python.

JIGSAW and JIGSAW-Python are built from source with ``mache jigsaw install``
rather than being dependencies of polaris, so listing and setting up tasks
must not need them; only writing a JIGSAW mesh does.
"""

import importlib
import pickle

import pytest

from polaris import Component
from polaris.mesh.spherical import QuasiUniformSphericalMeshStep
from polaris.mesh.spherical import jigsaw as jigsaw_module
from polaris.mesh.spherical.jigsaw import (
    JIGSAW_INSTALL_HINT,
    JigsawOptions,
    import_jigsawpy,
)


def test_an_option_that_was_not_set_is_none():
    """As in ``jigsawpy.jigsaw_jig_t``, which the options stand in for."""
    opts = JigsawOptions()

    assert opts.numthread is None
    opts.numthread = 4
    assert opts.numthread == 4


def test_options_survive_pickling():
    """Steps are pickled at setup and unpickled to run."""
    opts = JigsawOptions()
    opts.optm_iter = 64

    unpickled = pickle.loads(pickle.dumps(opts))

    assert unpickled.optm_iter == 64
    assert unpickled.hfun_hmax is None


def test_a_mesh_step_is_made_without_jigsawpy(monkeypatch):
    """Making a step is what ``polaris list`` and ``polaris setup`` do."""
    monkeypatch.setattr(jigsaw_module, 'import_module', _no_jigsawpy)

    step = QuasiUniformSphericalMeshStep(
        component=Component(name='mesh'), cell_width=240.0
    )

    assert step.opts.mesh_dims == 2


def test_a_missing_jigsawpy_says_how_to_install_it(monkeypatch):
    monkeypatch.setattr(jigsaw_module, 'import_module', _no_jigsawpy)

    with pytest.raises(ImportError, match='mache jigsaw install'):
        import_jigsawpy()


def test_the_options_become_a_jigsaw_jig():
    jigsawpy = pytest.importorskip('jigsawpy')
    opts = JigsawOptions()
    opts.mesh_dims = 2
    opts.optm_qtol = 1.0e-6

    jig = opts.to_jig()

    assert isinstance(jig, jigsawpy.jigsaw_jig_t)
    assert jig.mesh_dims == 2
    assert jig.optm_qtol == 1.0e-6
    assert jig.hfun_hmax is None


def _no_jigsawpy(name):
    if name.split('.')[0] == 'jigsawpy':
        raise ModuleNotFoundError(JIGSAW_INSTALL_HINT, name='jigsawpy')
    return importlib.import_module(name)
