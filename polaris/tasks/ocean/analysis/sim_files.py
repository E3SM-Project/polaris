"""
Helpers for locating the output of the simulation being analyzed.

This module is deliberately free of any dependence on
:py:class:`polaris.Step`, so that it can be unit tested and reused by every
analysis step that reads simulation output.
"""

import os
from typing import List, NamedTuple, Optional

from polaris.yaml import PolarisYaml


class SimFile(NamedTuple):
    """
    One file of simulation output, together with the date it covers

    Attributes
    ----------
    path : str
        The absolute path to the file

    year : int or None
        The simulation year the file covers, or ``None`` if the file-name
        template has no ``$Y`` in it

    month : int or None
        The month the file covers, or ``None`` if the file-name template has
        no ``$M`` in it
    """

    path: str
    year: Optional[int]
    month: Optional[int]


def year_range_key(start_year, end_year):
    """
    Get the key for a range of years, used both for step subdirectories and
    for the names of published files

    The zero-padded convention matches the one ``ncclimo`` already uses in its
    output file names.

    Parameters
    ----------
    start_year : int
        The first year of the range, inclusive

    end_year : int
        The last year of the range, inclusive

    Returns
    -------
    key : str
        The range key, e.g. ``'0021-0040'``
    """
    return f'{start_year:04d}-{end_year:04d}'


def expand_template(template, start_year, end_year, simulation_path=None):
    """
    Expand a file-name template over a range of years

    ``$Y`` is replaced by the four-digit year and ``$M`` by the two-digit
    month.  A template with no ``$M`` gives one file per year and a template
    with neither gives a single file, which is the case for the analysis
    output Omega writes to one file for a whole run.

    Parameters
    ----------
    template : str
        The file-name template, absolute or relative to ``simulation_path``

    start_year : int
        The first year to expand over, inclusive

    end_year : int
        The last year to expand over, inclusive

    simulation_path : str, optional
        The directory a relative template is resolved against

    Returns
    -------
    sim_files : list of SimFile
        The expanded files, in chronological order
    """
    _check_template(template)

    if not os.path.isabs(template):
        if simulation_path is None:
            raise ValueError(
                f'The file-name template "{template}" is relative but no '
                f'simulation_path was given to resolve it against.'
            )
        template = os.path.join(simulation_path, template)
    template = os.path.abspath(template)

    if start_year > end_year:
        raise ValueError(
            f'The start year {start_year} is after the end year {end_year}.'
        )

    has_year = '$Y' in template
    has_month = '$M' in template

    if not has_year:
        # a template with no date in it describes a single file covering the
        # whole run
        return [SimFile(path=template, year=None, month=None)]

    sim_files = []
    for year in range(start_year, end_year + 1):
        path = template.replace('$Y', f'{year:04d}')
        if not has_month:
            sim_files.append(SimFile(path=path, year=year, month=None))
            continue
        for month in range(1, 13):
            sim_files.append(
                SimFile(
                    path=path.replace('$M', f'{month:02d}'),
                    year=year,
                    month=month,
                )
            )

    return sim_files


def check_files_exist(sim_files, description, option_name):
    """
    Check that every expanded file exists, reporting the missing years and
    months rather than a bare list of paths

    Parameters
    ----------
    sim_files : list of SimFile
        The files to check, as returned by :py:func:`expand_template`

    description : str
        A short description of what the files are, used in the error message,
        e.g. ``'monthly-mean'``

    option_name : str
        The name of the config option in ``[ocean_analysis]`` that sets the
        template these files came from, so that the error says what to fix

    Raises
    ------
    FileNotFoundError
        If any of the files is missing
    """
    missing = [sim_file for sim_file in sim_files if not _exists(sim_file)]
    if not missing:
        return

    lines = [
        f'{len(missing)} of {len(sim_files)} {description} files are missing:'
    ]
    lines.extend(_describe_missing(missing))
    lines.append(
        f'Check the year range and the [ocean_analysis] {option_name} '
        f'option (or the Omega configuration file it defaults to).'
    )
    raise FileNotFoundError('\n'.join(lines))


class AnalysisStream(NamedTuple):
    """
    One output stream of an Omega analysis group

    Attributes
    ----------
    filename : str
        The file-name template Omega builds for the stream, which may contain
        ``$Y`` and ``$M``

    period : str
        The period of the time reduction or of the snapshots, e.g. ``'1Month'``

    is_reduction : bool
        Whether the stream holds time means rather than snapshots
    """

    filename: str
    period: str
    is_reduction: bool


class OmegaConfig:
    """
    The configuration file of the simulation being analyzed

    Polaris reads the simulation's own Omega configuration so that the mesh,
    the output streams and their file-name templates do not have to be
    restated by hand.  This is the one place Polaris depends on the *shape* of
    Omega's configuration rather than on its output, so every method here
    reports what it did not find rather than raising from deep inside a
    lookup.

    Attributes
    ----------
    filename : str
        The absolute path to the Omega configuration file

    streams : dict
        The contents of the ``IOStreams`` section

    options : dict
        The remaining options under the ``Omega`` section
    """

    def __init__(self, filename, streams, options):
        self.filename = filename
        self.streams = streams
        self.options = options

    def stream_status(self, stream_name):
        """
        Report whether an ``IOStreams`` entry can supply a file name

        Parameters
        ----------
        stream_name : str
            The name of the stream, e.g. ``'History'``

        Returns
        -------
        status : str
            ``'ok'``, ``'missing'`` if there is no such stream, or
            ``'no_filename'`` if the stream is there but names no file (a
            stream that uses a pointer file, for instance)
        """
        if stream_name not in self.streams:
            return 'missing'
        if not self.streams[stream_name].get('Filename'):
            return 'no_filename'
        return 'ok'

    def stream_filename(self, stream_name):
        """
        Get the file name or file-name template of an ``IOStreams`` entry

        Parameters
        ----------
        stream_name : str
            The name of the stream, e.g. ``'History'``

        Returns
        -------
        filename : str or None
            The file name, or ``None`` if the stream is absent or names no
            file
        """
        if self.stream_status(stream_name) != 'ok':
            return None
        return str(self.streams[stream_name]['Filename'])

    def analysis_group_status(self, group_name):
        """
        Report whether an analysis group is writing output

        Parameters
        ----------
        group_name : str
            The name of the analysis group, e.g. ``'GlobalStats'``

        Returns
        -------
        status : str
            ``'ok'``, ``'missing'`` if the simulation has no such group, or
            ``'disabled'`` if it has one that is turned off
        """
        groups = self.options.get('Analysis', {})
        if group_name not in groups:
            return 'missing'
        if not groups[group_name].get('Enable', True):
            return 'disabled'
        return 'ok'

    def analysis_streams(self, group_name):
        """
        Get the output streams an analysis group writes

        The file names are reconstructed the way Omega's analysis manager
        builds them, as ``<prefix>_<period><TimeStats|Instants><template>``.
        Time reductions come first, since a time mean is what analysis wants
        when a group writes both.

        Parameters
        ----------
        group_name : str
            The name of the analysis group, e.g. ``'GlobalStats'``

        Returns
        -------
        streams : list of AnalysisStream
            The streams the group writes, empty if the group is absent or
            disabled
        """
        if self.analysis_group_status(group_name) != 'ok':
            return []

        group = self.options['Analysis'][group_name]
        filename = group.get('Filename')
        if not filename:
            return []

        streams: List[AnalysisStream] = []
        for period in group.get('ReductionPeriod', []) or []:
            streams.append(
                AnalysisStream(
                    filename=_omega_analysis_filename(
                        str(filename), str(period), is_reduction=True
                    ),
                    period=str(period),
                    is_reduction=True,
                )
            )
        for period in group.get('SnapshotPeriod', []) or []:
            streams.append(
                AnalysisStream(
                    filename=_omega_analysis_filename(
                        str(filename), str(period), is_reduction=False
                    ),
                    period=str(period),
                    is_reduction=False,
                )
            )
        return streams


def read_omega_config(filename):
    """
    Read the configuration file of the simulation being analyzed

    Parameters
    ----------
    filename : str
        The path to the simulation's Omega configuration file

    Returns
    -------
    omega_config : OmegaConfig
        The parsed configuration

    Raises
    ------
    FileNotFoundError
        If there is no file at ``filename``

    ValueError
        If the file does not look like an Omega configuration
    """
    filename = os.path.abspath(filename)
    if not os.path.exists(filename):
        raise FileNotFoundError(
            f'No Omega configuration file at {filename}.  Set the '
            f'[ocean_analysis] omega_config_filename option to the '
            f'configuration file of the simulation being analyzed, or leave '
            f'it empty and set the mesh and file-name template options by '
            f'hand.'
        )

    try:
        yaml = PolarisYaml.read(filename, streams_section='IOStreams')
    except Exception as exception:
        raise ValueError(
            f'Could not parse {filename} as an Omega configuration file: '
            f'{exception}'
        ) from exception

    if yaml.model != 'Omega':
        raise ValueError(
            f'{filename} does not look like an Omega configuration file: its '
            f'top-level section is "{yaml.model}" rather than "Omega".'
        )

    return OmegaConfig(
        filename=filename, streams=yaml.streams, options=yaml.configs
    )


def _exists(sim_file):
    """Whether a simulation file is present, following any symlink"""
    return os.path.exists(sim_file.path)


def _describe_missing(missing):
    """Summarize missing files as one line per year"""
    if missing[0].year is None:
        return [f'  {sim_file.path}' for sim_file in missing]

    by_year: dict = {}
    for sim_file in missing:
        by_year.setdefault(sim_file.year, []).append(sim_file.month)

    lines = []
    for year, months in sorted(by_year.items()):
        if months[0] is None:
            lines.append(f'  year {year:04d}')
        else:
            month_list = ', '.join(f'{month:02d}' for month in sorted(months))
            lines.append(f'  year {year:04d}: months {month_list}')
    return lines


def _check_template(template):
    """Complain about date fields we do not know how to expand"""
    unsupported = [
        field for field in ['$D', '$h', '$m', '$s'] if field in template
    ]
    if unsupported:
        raise ValueError(
            f'The file-name template "{template}" contains '
            f'{", ".join(unsupported)}, which the analysis cannot expand.  '
            f'Only $Y and $M are supported, since the analysis reads output '
            f'written no more often than monthly.'
        )


def _omega_analysis_filename(filename, period, is_reduction):
    """
    Build the file name Omega's analysis manager gives an output stream

    This mirrors ``AnalysisGroup::createAnalysisGroupStreams()`` in Omega,
    which splits the configured name at the first ``$``, absorbing a trailing
    ``.`` or ``_`` from the prefix into the timestamp template, and then
    inserts the period and the kind of output between the two.
    """
    position = filename.find('$')
    if position == -1:
        prefix = filename
        template = ''
    elif position == 0:
        prefix = ''
        template = filename
    elif filename[position - 1] in ('.', '_'):
        prefix = filename[: position - 1]
        template = filename[position - 1 :]
    else:
        prefix = filename[:position]
        template = filename[position:]

    kind = 'TimeStats' if is_reduction else 'Instants'
    return f'{prefix}_{period}{kind}{template}'
