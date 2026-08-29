import os

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.analysis.sim_files import SimulationFiles


class AnalysisStep(OceanIOStep):
    """
    A step of the ocean analysis suite

    Every analysis step covers a range of simulation years and reads some of
    the simulation's output, so both live here rather than being repeated by
    each product.

    Attributes
    ----------
    start_year : int
        The first year of the range this step covers, inclusive

    end_year : int
        The last year of the range this step covers, inclusive

    input_filenames : list of str
        The local names of the simulation files symlinked into the step's
        work directory, in the order they were added
    """

    #: Whether this step makes products for the published gallery, and so
    #: writes a manifest fragment describing them.  A step that only computes
    #: intermediate results for other steps to plot sets this to ``False``,
    #: which keeps the ``publish`` step from depending on it and from
    #: reporting the fragment it was never going to write.
    makes_products = True

    def __init__(
        self, component, name, subdir, start_year, end_year, **kwargs
    ):
        """
        Create a new analysis step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step, which ends in the range key so
            that a step covering a different range is a different step

        start_year : int
            The first year of the range this step covers, inclusive

        end_year : int
            The last year of the range this step covers, inclusive

        kwargs
            Keyword arguments passed on to
            :py:class:`polaris.ocean.model.OceanIOStep`
        """
        super().__init__(
            component=component, name=name, subdir=subdir, **kwargs
        )
        self.start_year = start_year
        self.end_year = end_year
        self.input_filenames: list = []

    def get_sim_files(self):
        """
        Get the simulation's files, reporting where each path came from

        This is called from ``setup()``, where a step has no logger yet, so
        the report goes to the terminal along with the rest of what
        ``polaris setup`` prints.

        Returns
        -------
        sim_files : polaris.tasks.ocean.analysis.sim_files.SimulationFiles
            The files of the simulation being analyzed
        """
        sim_files = SimulationFiles(self.config)
        print(
            f'{self.name} ({self.start_year}-{self.end_year}): simulation at '
            f'{sim_files.simulation_path} '
            f'(from {sim_files.simulation_path_source})'
        )
        return sim_files

    def add_sim_input_file(self, path, filename=None):
        """
        Symlink one file of simulation output into the step's work directory

        Parameters
        ----------
        path : str
            The absolute path to the file

        filename : str, optional
            The local name of the symlink; defaults to the base name of
            ``path``

        Returns
        -------
        filename : str
            The local name of the symlink
        """
        if filename is None:
            filename = os.path.basename(path)
        if filename in self.input_filenames:
            raise ValueError(
                f'Two files of simulation output would be linked into '
                f'{self.name} as "{filename}".  The second is {path}.'
            )
        self.add_input_file(filename=filename, target=path)
        self.input_filenames.append(filename)
        return filename

    def add_sim_input_files(self, sim_files):
        """
        Symlink a list of simulation files into the step's work directory

        Parameters
        ----------
        sim_files : list of polaris.tasks.ocean.analysis.sim_files.SimFile
            The files to link, as returned by the methods of
            :py:class:`~polaris.tasks.ocean.analysis.sim_files.SimulationFiles`
        """
        for sim_file in sim_files:
            self.add_sim_input_file(sim_file.path)

    def log_inputs(self):
        """
        Report the simulation files this step reads

        This is what the steps do in place of their product while the suite
        is being scaffolded, and it is worth keeping afterwards: it is the
        record of what a step actually read, in the step's own log.
        """
        self.logger.info(
            f'{self.name}: years {self.start_year} through {self.end_year}, '
            f'{len(self.input_filenames)} input files'
        )
        for filename in self.input_filenames:
            self.logger.info(f'  {self.work_path(filename)}')
