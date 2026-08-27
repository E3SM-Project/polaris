"""
Helpers for locating the output of the simulation being analyzed.

This module is deliberately free of any dependence on
:py:class:`polaris.Step`, so that it can be unit tested and reused by every
analysis step that reads simulation output.
"""

import os
from typing import NamedTuple, Optional


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
