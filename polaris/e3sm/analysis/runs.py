"""
The runs E3SM analysis compares: an E3SM case, and a standalone MPAS run
that Polaris set up in a work directory

Both find a model's output from the streams file the model read, so the
analysis reads them through the same few methods.
"""

import os

from polaris.e3sm.analysis.case import E3smCase
from polaris.namelist import ingest
from polaris.streams import find_stream_files, get_stream, read_file

#: The namelist each model reads in its E3SM run directory
_E3SM_NAMELISTS = {'mpaso': 'mpaso_in', 'mali': 'mali_in'}


class E3smRun:
    """
    A model's output in an E3SM case

    Attributes
    ----------
    case : polaris.e3sm.analysis.case.E3smCase
        The case

    model : str
        The model, ``mpaso`` or ``mali``
    """

    def __init__(self, case_dir, model):
        """
        Read the case

        Parameters
        ----------
        case_dir : str
            The case directory

        model : {'mpaso', 'mali'}
            The model whose output is read
        """
        self.case = E3smCase(case_dir)
        self.model = model

    @property
    def initial_condition(self):
        """The model's initial condition, which holds its mesh"""
        variable = {'mpaso': 'MPASO_IC_FILE', 'mali': 'MALI_IC_FILE'}
        return self.case.get_value(variable[self.model])

    @property
    def mesh_file(self):
        """The file with the model's mesh, its initial condition"""
        return self.initial_condition

    def find_stream_files(self, stream_name):
        """
        Find the files of one of the model's streams

        Parameters
        ----------
        stream_name : str
            The stream, such as ``timeSeriesStatsMonthlyOutput``

        Returns
        -------
        stream_files : list of polaris.streams.StreamFile
            The files, in order of their dates
        """
        return self.case.find_stream_files(self.model, stream_name)

    def input_filename(self, stream_name):
        """
        Get the file an input stream of one file reads

        Parameters
        ----------
        stream_name : str
            The stream, such as ``tidal_forcing_mask``

        Returns
        -------
        filename : str
            The file, relative paths taken from the run directory
        """
        stream = get_stream(self.case.read_streams(self.model), stream_name)
        return os.path.join(
            self.case.run_dir, stream.attrib['filename_template']
        )

    def namelist_option(self, option):
        """
        Get an option from the namelist the model read

        Parameters
        ----------
        option : str
            The option, such as ``config_drying_min_cell_height``

        Returns
        -------
        value : str
            The option's value as written in the namelist
        """
        filename = os.path.join(self.case.run_dir, _E3SM_NAMELISTS[self.model])
        return _namelist_option(filename, option)


class StandaloneRun:
    """
    A standalone MPAS-Ocean run in the work directory of a Polaris forward
    step

    Attributes
    ----------
    work_dir : str
        The absolute path to the forward step's work directory
    """

    def __init__(self, work_dir):
        """
        Find the run

        Parameters
        ----------
        work_dir : str
            The forward step's work directory, holding ``streams.ocean``,
            ``namelist.ocean`` and ``init.nc``
        """
        self.work_dir = os.path.abspath(work_dir)
        for filename in ['streams.ocean', 'namelist.ocean', 'init.nc']:
            if not os.path.exists(os.path.join(self.work_dir, filename)):
                raise FileNotFoundError(
                    f'{self.work_dir} has no {filename}, so it is not the '
                    f'work directory of an MPAS-Ocean forward step.'
                )

    @property
    def initial_condition(self):
        """The run's initial condition"""
        return os.path.realpath(os.path.join(self.work_dir, 'init.nc'))

    @property
    def mesh_file(self):
        """
        The file with the run's mesh: ``mesh.nc`` beside the initial
        condition if there is one, since an initial condition from an SSH
        adjustment holds only the state, or the initial condition otherwise
        """
        mesh = os.path.join(self.work_dir, 'mesh.nc')
        if os.path.exists(mesh):
            return os.path.realpath(mesh)
        return self.initial_condition

    def find_stream_files(self, stream_name):
        """
        Find the files of one of the run's streams

        Parameters
        ----------
        stream_name : str
            The stream, such as ``timeSeriesStatsMonthlyOutput``

        Returns
        -------
        stream_files : list of polaris.streams.StreamFile
            The files, in order of their dates
        """
        tree = read_file(os.path.join(self.work_dir, 'streams.ocean'))
        stream = get_stream(tree, stream_name)
        return find_stream_files(
            stream.attrib['filename_template'], [self.work_dir]
        )

    def input_filename(self, stream_name):
        """
        Get the file an input stream of one file reads

        Parameters
        ----------
        stream_name : str
            The stream, such as ``tidal_forcing_mask``

        Returns
        -------
        filename : str
            The file, relative paths taken from the work directory
        """
        tree = read_file(os.path.join(self.work_dir, 'streams.ocean'))
        stream = get_stream(tree, stream_name)
        return os.path.join(self.work_dir, stream.attrib['filename_template'])

    def namelist_option(self, option):
        """
        Get an option from the namelist the run read

        Parameters
        ----------
        option : str
            The option, such as ``config_drying_min_cell_height``

        Returns
        -------
        value : str
            The option's value as written in the namelist
        """
        return _namelist_option(
            os.path.join(self.work_dir, 'namelist.ocean'), option
        )


def select_months(stream_files, start_year, end_year):
    """
    Select the monthly files in a range of years, and check that no month
    between the first and the last is missing

    Parameters
    ----------
    stream_files : list of polaris.streams.StreamFile
        The files of a stream of monthly means, named for the start of each
        month

    start_year, end_year : int
        The range of years, inclusive

    Returns
    -------
    selected : list of polaris.streams.StreamFile
        The files of the months in the range, in order
    """
    selected = [
        stream_file
        for stream_file in stream_files
        if start_year <= stream_file.year <= end_year
    ]
    if not selected:
        raise ValueError(
            f'No monthly means are in years {start_year} through {end_year}.'
        )
    months = [12 * (f.year - 1) + f.month - 1 for f in selected]
    missing = sorted(set(range(months[0], months[-1] + 1)) - set(months))
    if missing:
        names = [
            f'{1 + month // 12:04d}-{1 + month % 12:02d}' for month in missing
        ]
        raise ValueError(
            f'The monthly means of {", ".join(names)} are missing, between '
            f'the first and last month found.'
        )
    return selected


def month_range_key(stream_files):
    """
    Get the key for the months a list of monthly files covers, for step
    subdirectories and published names

    Parameters
    ----------
    stream_files : list of polaris.streams.StreamFile
        Monthly files in order

    Returns
    -------
    key : str
        For example ``0001-01_0020-12``
    """
    first = stream_files[0]
    last = stream_files[-1]
    return (
        f'{first.year:04d}-{first.month:02d}_{last.year:04d}-{last.month:02d}'
    )


def _namelist_option(filename, option):
    """Find an option in any record of a namelist"""
    for record in ingest(filename).values():
        if option in record:
            return record[option]
    raise KeyError(f'{filename} has no option {option}.')
