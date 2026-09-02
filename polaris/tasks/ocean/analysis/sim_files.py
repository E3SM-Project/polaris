"""
Helpers for locating the output of the simulation being analyzed.

This module is deliberately free of any dependence on
:py:class:`polaris.Step`, so that it can be unit tested and reused by every
analysis step that reads simulation output.
"""

import os
import re
from glob import glob
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


def check_files_exist(
    sim_files, description, source, template=None, simulation_path=None
):
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

    source : str
        A description of where the file-name template came from, so that the
        error says where to look, e.g. ``'the History stream in
        /path/omega.yml'``

    template : str, optional
        The template the files were expanded from.  Given it, the error also
        says which years the simulation did write, which is usually the
        answer the reader wants.

    simulation_path : str, optional
        The directory a relative template is resolved against

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
    lines.append(f'They are named by {source}.')
    available = _years_available(template, simulation_path)
    if available:
        first, last = available[0], available[-1]
        gaps = len(available) < last - first + 1
        span = f'{first}-{last}' + (', with gaps' if gaps else '')
        lines.append(
            f'The simulation wrote years {span}.  Set start_year and '
            f'end_year within that range.'
        )
    else:
        lines.append(
            'Check the year range and that the simulation wrote this output '
            'for those years.'
        )
    raise FileNotFoundError('\n'.join(lines))


def _years_available(template, simulation_path):
    """
    Find the years the simulation actually wrote, for the error message

    This looks at the simulation directory, which the analysis otherwise
    never does: a range is declared by the user rather than discovered, so
    that the same request always means the same thing.  Discovering it here
    only turns "some files are missing" into the answer the reader wants,
    and nothing outside this error path depends on it.
    """
    if template is None or '$Y' not in template:
        return []
    if not os.path.isabs(template) and simulation_path is not None:
        template = os.path.join(simulation_path, template)
    pattern = template.replace('$Y', '[0-9]' * 4).replace('$M', '[0-9]' * 2)
    matcher = re.escape(template)
    matcher = matcher.replace(re.escape('$Y'), r'(?P<year>[0-9]{4})')
    matcher = matcher.replace(re.escape('$M'), r'[0-9]{2}')
    years = set()
    for path in glob(pattern):
        found = re.fullmatch(matcher, path)
        if found:
            years.add(int(found.group('year')))
    return sorted(years)


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


class SimulationFiles:
    """
    The files of the simulation being analyzed

    The simulation's own Omega configuration is the analysis' description of
    where its output lives: the mesh, the vertical coordinate and every output
    stream are read from it, so that none of them have to be restated in a
    Polaris config file.  An Omega run always writes one, so its absence is an
    error rather than a case to fall back from.

    Attributes
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    omega_config : OmegaConfig
        The simulation's Omega configuration

    simulation_path : str
        The directory that relative file names are resolved against

    simulation_path_source : str
        Where ``simulation_path`` came from, for reporting

    simulation_name : str
        A short name for the simulation, used in plot titles and file names
    """

    def __init__(self, config, log=print):
        """
        Resolve the simulation's paths from its Omega configuration

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The config options for the analysis

        log : callable, optional
            Where to report each resolved path and its source.  The default,
            ``print``, is what a step wants during ``setup()``, where it has
            no logger yet; at run time a step passes ``self.logger.info``.
        """
        self.config = config
        self.log = log

        _check_model(config)

        section = config['ocean_analysis']
        omega_config_filename = section.get('omega_config_filename').strip()
        if not omega_config_filename:
            raise ValueError(
                'Set the [ocean_analysis] omega_config_filename option to '
                "the simulation's Omega configuration file.  It is how the "
                'analysis finds the mesh and the output streams, and an '
                'Omega run always writes one.'
            )
        self.omega_config = read_omega_config(omega_config_filename)
        self.simulation_path = self._resolve_simulation_path()
        self.simulation_name = section.get('simulation_name')

    def mesh_filename(self):
        """
        Get the horizontal mesh file

        Returns
        -------
        filename : str
            The absolute path to the mesh file
        """
        return self._resolve_stream_path(
            option_name='mesh_filename',
            stream_name='HorzMeshIn',
            description='horizontal mesh',
        )

    def vert_coord_filename(self):
        """
        Get the vertical-coordinate file

        Returns
        -------
        filename : str
            The absolute path to the vertical-coordinate file
        """
        return self._resolve_stream_path(
            option_name='vert_coord_filename',
            stream_name='InitialVertCoord',
            description='vertical coordinate',
        )

    def monthly_mean_files(self, start_year, end_year):
        """
        Get the monthly-mean output files covering a range of years

        Parameters
        ----------
        start_year : int
            The first year of the range, inclusive

        end_year : int
            The last year of the range, inclusive

        Returns
        -------
        sim_files : list of SimFile
            The monthly-mean files, which are known to exist
        """
        template = self._stream_template(
            stream_name='History', description='monthly means'
        )
        return self._expand_and_check(
            template=template,
            start_year=start_year,
            end_year=end_year,
            description='monthly-mean',
            source=f'the History stream in {self.omega_config.filename}',
        )

    def global_stats_files(self, start_year, end_year):
        """
        Get the global statistics output files covering a range of years

        Parameters
        ----------
        start_year : int
            The first year of the range, inclusive

        end_year : int
            The last year of the range, inclusive

        Returns
        -------
        sim_files : list of SimFile
            The global statistics files, which are known to exist
        """
        template = self._analysis_template(
            group_name='GlobalStats',
            description='global statistics',
            required=True,
        )
        assert template is not None
        return self._expand_and_check(
            template=template,
            start_year=start_year,
            end_year=end_year,
            description='global statistics',
            source=(
                f'the GlobalStats analysis group in '
                f'{self.omega_config.filename}'
            ),
        )

    def moc_files(self, start_year, end_year):
        """
        Get the meridional overturning circulation output files covering a
        range of years

        Omega's MOC diagnostic is new, so a simulation that does not write it
        is an ordinary case rather than an error.

        Parameters
        ----------
        start_year : int
            The first year of the range, inclusive

        end_year : int
            The last year of the range, inclusive

        Returns
        -------
        sim_files : list of SimFile or None
            The MOC files, which are known to exist, or ``None`` if the
            simulation does not write MOC output
        """
        template = self._analysis_template(
            group_name='Moc',
            description='meridional overturning circulation',
            required=False,
        )
        if template is None:
            return None
        return self._expand_and_check(
            template=template,
            start_year=start_year,
            end_year=end_year,
            description='MOC',
            source=f'the Moc analysis group in {self.omega_config.filename}',
        )

    def _resolve_simulation_path(self):
        """Get the directory that relative file names are resolved against"""
        simulation_path = self.config.get(
            'ocean_analysis', 'simulation_path'
        ).strip()
        if simulation_path:
            source = '[ocean_analysis] simulation_path'
        else:
            simulation_path = os.path.dirname(self.omega_config.filename)
            source = 'the directory of the Omega configuration file'
        self.simulation_path_source = source
        return os.path.abspath(simulation_path)

    def _resolve_stream_path(self, option_name, stream_name, description):
        """
        Resolve a single file, either from a config option or from an Omega
        ``IOStreams`` entry
        """
        value = self.config.get('ocean_analysis', option_name).strip()
        if value:
            self.log(
                f'{description}: {value} (from [ocean_analysis] {option_name})'
            )
        else:
            value = self._stream_template(stream_name, description)
        return self._absolute(value)

    def _stream_template(self, stream_name, description):
        """Get a file name or template from an Omega ``IOStreams`` entry"""
        status = self.omega_config.stream_status(stream_name)
        if status == 'missing':
            raise ValueError(
                f'{self.omega_config.filename} has no {stream_name} stream, '
                f'so the analysis cannot find the {description} of the '
                f'simulation.'
            )
        if status == 'no_filename':
            raise ValueError(
                f'The {stream_name} stream in '
                f'{self.omega_config.filename} names no file, so the '
                f'analysis cannot find the {description} of the simulation.'
            )

        value = self.omega_config.stream_filename(stream_name)
        assert value is not None
        self.log(
            f'  {description}: {value} '
            f"(from the Omega config's {stream_name} stream)"
        )
        return value

    def _analysis_template(self, group_name, description, required):
        """Get a file-name template from an Omega analysis group"""
        reason = self._analysis_group_problem(group_name)
        if reason is None:
            streams = self.omega_config.analysis_streams(group_name)
            stream = _preferred_analysis_stream(streams)
            if stream is None:
                reason = (
                    f'the {group_name} analysis group in '
                    f'{self.omega_config.filename} writes no output streams'
                )
            else:
                kind = 'time-mean' if stream.is_reduction else 'snapshot'
                self.log(
                    f'  {description}: {stream.filename} (from the Omega '
                    f"config's {group_name} group, the {stream.period} "
                    f'{kind} stream)'
                )
                return stream.filename

        if required:
            raise ValueError(
                f'The analysis needs the {description} of the simulation, '
                f'but {reason}.'
            )
        self.log(f'  no {description} output: {reason}')
        return None

    def _analysis_group_problem(self, group_name):
        """
        Describe why an analysis group cannot supply a template, if it cannot
        """
        status = self.omega_config.analysis_group_status(group_name)
        if status == 'missing':
            return (
                f'{self.omega_config.filename} has no {group_name} analysis '
                f'group, so the simulation wrote no such output'
            )
        if status == 'disabled':
            return (
                f'the {group_name} analysis group in '
                f'{self.omega_config.filename} is turned off, so the '
                f'simulation wrote no such output'
            )
        return None

    def _expand_and_check(
        self, template, start_year, end_year, description, source
    ):
        """Expand a template over a year range and check that it all exists"""
        sim_files = expand_template(
            template=template,
            start_year=start_year,
            end_year=end_year,
            simulation_path=self.simulation_path,
        )
        check_files_exist(
            sim_files=sim_files,
            description=description,
            source=source,
            template=template,
            simulation_path=self.simulation_path,
        )
        return sim_files

    def _absolute(self, filename):
        """Resolve a file name against the simulation path"""
        if not os.path.isabs(filename):
            filename = os.path.join(self.simulation_path, filename)
        return os.path.abspath(filename)


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


def _preferred_analysis_stream(streams):
    """
    Pick the analysis stream to read: a time mean if the group wrote one,
    otherwise a snapshot
    """
    for stream in streams:
        if stream.is_reduction:
            return stream
    if streams:
        return streams[0]
    return None


def _check_model(config):
    """
    Complain unless the simulation was run with Omega

    MPAS-Ocean output is not supported.  Reading it would need a translator
    from its namelists and streams into the form this module reads, which is
    a separate piece of work.
    """
    model = config.get('ocean', 'model')
    if model != 'omega':
        raise ValueError(
            f'The analysis suite reads Omega output, but [ocean] model is '
            f'"{model}".  Set --model omega at setup if the simulation was '
            f'run with Omega.  MPAS-Ocean output is not supported: reading '
            f'it would need a translator from its namelists and streams '
            f'into the form the analysis reads.'
        )
