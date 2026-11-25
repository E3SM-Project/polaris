"""
Access to JIGSAW-Python, imported only by the steps that build a mesh

Polaris needs a newer JIGSAW and JIGSAW-Python than conda-forge provides, so
they are not dependencies of the polaris package: ``mache jigsaw install``
builds them from source into the environment.  Importing ``jigsawpy`` only
where a mesh is written lets every other command, and every task that does
not build a JIGSAW mesh, work without it.
"""

from importlib import import_module
from typing import Any

JIGSAW_INSTALL_HINT = (
    'Building a JIGSAW mesh needs JIGSAW and JIGSAW-Python, which are not '
    'installed in this environment. Install them from source with '
    '`mache jigsaw install`, as described under "JIGSAW, for tasks that '
    'build meshes" in the Polaris Quick Start for Users.'
)


def import_jigsawpy():
    """
    Import JIGSAW-Python, explaining how to install it if it is missing

    Returns
    -------
    jigsawpy : module
        The ``jigsawpy`` package
    """
    try:
        return import_module('jigsawpy')
    except ImportError as err:
        raise ImportError(JIGSAW_INSTALL_HINT) from err


def write_jigsaw_config(opts):
    """
    Write JIGSAW options to their config file, ``opts.jcfg_file``

    Parameters
    ----------
    opts : polaris.mesh.spherical.jigsaw.JigsawOptions
        The JIGSAW options to write
    """
    import_jigsawpy()
    savejig = import_module('jigsawpy.savejig').savejig
    savejig(opts.jcfg_file, opts.to_jig())


class JigsawOptions:
    """
    JIGSAW options gathered before JIGSAW-Python is needed

    As in ``jigsawpy.jigsaw_jig_t``, an option that has not been set is
    ``None``.  ``to_jig()`` makes the ``jigsaw_jig_t`` that JIGSAW-Python
    writes, so a step can be created, set up and pickled without JIGSAW.
    """

    def __getattr__(self, name: str) -> Any:
        # only called for attributes that have not been set; leave private
        # and special names to the normal lookup, which pickle and copy rely
        # on
        if name.startswith('_'):
            raise AttributeError(name)
        return None

    def __setattr__(self, name: str, value: Any) -> None:
        # any JIGSAW option may be set; declared so that type checkers know
        super().__setattr__(name, value)

    def to_jig(self):
        """
        Make a ``jigsawpy.jigsaw_jig_t`` holding these options

        Returns
        -------
        jig : jigsawpy.jigsaw_jig_t
            The JIGSAW options
        """
        jigsawpy = import_jigsawpy()
        jig = jigsawpy.jigsaw_jig_t()
        for name, value in vars(self).items():
            setattr(jig, name, value)
        return jig
