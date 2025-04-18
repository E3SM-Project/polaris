import os
from typing import Union

from mpas_tools.config import MpasConfigParser


class PolarisConfigParser(MpasConfigParser):
    """
    A "meta" config parser that keeps a dictionary of config parsers and their
    sources to combine when needed.  The custom config parser allows provenance
    of the source of different config options and allows the "user" config
    options to always take precedence over other config options (even if they
    are added later).

    This version simply overrides the ``combine()`` method to also ensure that
    certain paths are absolute, rather than relative.

    Attributes
    ----------
    filepath : str
        A filepath within the work directory where this config will be written
        out

    tasks : set of polaris.Task
        A list of tasks that use this config
    """

    def __init__(self, filepath=None):
        """
        Make a new (empty) config parser

        Parameters
        ----------
        filepath : str, optional
            A filepath within the work directory where this config will be
            written out
        """
        super().__init__()
        self.filepath: Union[str, None] = filepath
        self.tasks = set()

    def setup(self):
        """
        A method that can be overridden to add config options during polaris
        setup
        """
        pass

    def combine(self, raw=False):
        """
        Combine the config files into one

        Parameters
        ----------
        raw : bool, optional
            Whether to combine config "raw" config options, rather than using
            extended interpolation
        """
        super().combine(raw=raw)
        self._ensure_absolute_paths()

    def _ensure_absolute_paths(self):
        """
        make sure all paths in the paths, namelists, streams, and executables
        sections are absolute paths
        """
        config = self.combined
        for section in ['paths', 'namelists', 'streams', 'executables']:
            if not config.has_section(section):
                continue
            for option, value in config.items(section):
                # not safe to make paths that start with other config options
                # into absolute paths
                if not value.startswith('$'):
                    value = os.path.abspath(value)
                    config.set(section, option, value)
