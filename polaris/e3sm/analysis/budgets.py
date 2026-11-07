"""
The budgets the E3SM coupler writes to its log when ``BUDGETS=TRUE``

The coupler prints each budget as a table of global means: a header naming
the budget, its units, the period and the date at the end of the period, a
line of component names, and one row per term.  Values are written with the
Fortran format ``f15.8`` after a 4-character indent and a 12-character name,
so they are read by position rather than split on spaces, which a value of
15 characters would not survive.
"""

import gzip
import re
from typing import NamedTuple

import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants

#: The header of a net budget table
_HEADER = re.compile(
    r'\(seq_diag_print_mct\)\s+NET (?P<budget>\w+) BUDGET '
    r'\((?P<units>[^)]*)\): period =\s*(?P<period>\w+): date =\s*'
    r'(?P<date>\d+)\s+(?P<seconds>\d+)'
)

#: The driver's start date and whether it skips the ocean's first coupling
#: interval, which it does at an initial start
_START_YMD = re.compile(r'\(seq_timemgr_clockInit\)\s+start_ymd\s+=\s*(\d+)')
_START_TOD = re.compile(r'\(seq_timemgr_clockInit\)\s+start_tod\s+=\s*(\d+)')
_SKIP_OCEAN = re.compile(r'skip init ocean run\s+=\s*(?P<skip>[TF])')

#: The width of the indent and row name, and of each value
_NAME_END = 16
_FIELD_WIDTH = 15

#: The scale of the printed values of each budget, which the coupler
#: multiplies by these factors before printing
_PRINT_SCALES = {
    'AREA': 1.0,
    'HEAT': 1.0,
    'WATER': 1.0e6,
    'SALT': 1.0e8,
}

#: The units of each budget once it is converted back to a total
_TOTAL_UNITS = {
    'AREA': 'm2',
    'HEAT': 'W',
    'WATER': 'kg s-1',
    'SALT': 'kg s-1',
}


class BudgetTable(NamedTuple):
    """
    One budget table from a coupler log

    Attributes
    ----------
    budget : str
        The budget: ``AREA``, ``HEAT``, ``WATER`` or ``SALT``

    period : str
        The period it averages over: ``inst``, ``daily``, ``monthly``,
        ``annual`` or ``all_time``

    year, month, day, seconds : int
        The model date at the end of the period

    units : str
        The units the table was printed in

    rows : list of str
        The terms of the budget, such as ``wpolar``, and ``*SUM*`` for the
        sum of the terms where the coupler prints it

    components : list of str
        The components, such as ``ocn`` and ``glc``, and ``*SUM*`` for their
        sum

    values : numpy.ndarray
        The printed values, with dimensions rows by components, and NaN
        where the value did not fit its field
    """

    budget: str
    period: str
    year: int
    month: int
    day: int
    seconds: int
    units: str
    rows: list
    components: list
    values: np.ndarray


def read_budget_tables(log_filenames):
    """
    Read the net budget tables from coupler logs, compressed or not

    Parameters
    ----------
    log_filenames : list of str
        The coupler logs, in the order they were written

    Returns
    -------
    tables : list of polaris.e3sm.analysis.budgets.BudgetTable
        The tables, in the order they were written
    """
    tables = []
    for filename in log_filenames:
        tables.extend(_parse_tables(_read_lines(filename)))
    return tables


def read_initial_start(log_filenames):
    """
    Find the date of a run's initial start in its coupler logs

    At an initial start, the driver skips the ocean's first coupling
    interval.  The coupler's ocean column books the ocean's initial export
    for that interval, which glc never receives, so the budgets that contain
    the start don't close by that amount.

    Parameters
    ----------
    log_filenames : list of str
        The coupler logs, in the order they were written

    Returns
    -------
    start : str or None
        The date of the latest initial start, ``YYYY-MM-DD_SSSSS`` as
        :py:func:`polaris.e3sm.analysis.budgets.budget_time_series` gives
        dates, or None if no log is from an initial start
    """
    start = None
    for filename in log_filenames:
        text = '\n'.join(_read_lines(filename))
        skip = _SKIP_OCEAN.search(text)
        ymd = _START_YMD.search(text)
        tod = _START_TOD.search(text)
        if skip is None or skip.group('skip') != 'T' or ymd is None:
            continue
        date = int(ymd.group(1))
        seconds = 0 if tod is None else int(tod.group(1))
        start = _format_date(
            date // 10000, (date // 100) % 100, date % 100, seconds
        )
    return start


def budget_time_series(tables, budget, period):
    """
    Gather one budget for one period into a time series of totals

    The coupler prints global means per unit area of the sphere, scaled for
    printing.  They are converted back to totals over the sphere with E3SM's
    radius: kg s-1 for water and salt, and W for heat.  A date that appears
    in more than one table, as it does when a run is restarted, takes the
    last.

    Parameters
    ----------
    tables : list of polaris.e3sm.analysis.budgets.BudgetTable
        Tables from :py:func:`read_budget_tables`

    budget : str
        The budget, such as ``WATER``

    period : str
        The period, such as ``monthly``

    Returns
    -------
    ds : xarray.Dataset
        The variable ``budget`` with dimensions ``Time``, ``row`` and
        ``component``, and coordinates ``date`` (``YYYY-MM-DD_SSSSS``) and
        the names of the rows and components
    """
    selected = dict()
    for table in tables:
        if table.budget == budget and table.period == period:
            date = _format_date(
                table.year, table.month, table.day, table.seconds
            )
            selected[date] = table
    if not selected:
        raise ValueError(
            f'The coupler logs hold no {budget} budget for the period '
            f'{period}.  Was the case run with BUDGETS=TRUE?'
        )
    dates = sorted(selected)
    first = selected[dates[0]]
    for date in dates:
        table = selected[date]
        if table.rows != first.rows or table.components != first.components:
            raise ValueError(
                f'The {budget} budget at {date} has different terms or '
                f'components than at {dates[0]}.'
            )

    radius = constants['SHR_CONST_REARTH']
    scale = 4.0 * np.pi * radius**2 / _PRINT_SCALES[budget]
    values = scale * np.stack([selected[date].values for date in dates])

    ds = xr.Dataset()
    ds['budget'] = (('Time', 'row', 'component'), values)
    ds.budget.attrs['units'] = _TOTAL_UNITS[budget]
    ds.budget.attrs['long_name'] = (
        f'{budget.lower()} budget, {period} mean, as a total over the sphere'
    )
    ds.coords['date'] = ('Time', dates)
    ds.coords['row'] = ('row', first.rows)
    ds.coords['component'] = ('component', first.components)
    return ds


def _read_lines(filename):
    """Read a log's lines, compressed or not"""
    opener = gzip.open if filename.endswith('.gz') else open
    with opener(filename, 'rt') as log:
        return log.read().splitlines()


def _format_date(year, month, day, seconds):
    """A date as ``YYYY-MM-DD_SSSSS``"""
    return f'{year:04d}-{month:02d}-{day:02d}_{seconds:05d}'


def _parse_tables(lines):
    """Parse every net budget table in a log's lines"""
    tables = []
    index = 0
    while index < len(lines):
        match = _HEADER.search(lines[index])
        if match is None:
            index += 1
            continue
        components = _parse_components(lines[index + 1])
        rows = []
        values = []
        index += 2
        while index < len(lines) and _is_row(lines[index]):
            name, row_values = _parse_row(lines[index], len(components))
            rows.append(name)
            values.append(row_values)
            index += 1
        date = int(match.group('date'))
        tables.append(
            BudgetTable(
                budget=match.group('budget'),
                period=match.group('period'),
                year=date // 10000,
                month=(date // 100) % 100,
                day=date % 100,
                seconds=int(match.group('seconds')),
                units=match.group('units'),
                rows=rows,
                components=components,
                values=np.array(values),
            )
        )
    return tables


def _parse_components(line):
    """Parse the component names over a table's columns"""
    fields = line[_NAME_END:]
    return [
        fields[start : start + _FIELD_WIDTH].strip()
        for start in range(0, len(fields.rstrip()), _FIELD_WIDTH)
    ]


def _is_row(line):
    """Whether a line is a row of a table: a name, then values"""
    return (
        len(line) > _NAME_END
        and line[:4] == '    '
        and bool(line[4:_NAME_END].strip())
    )


def _parse_row(line, count):
    """Parse a row's name and values, with NaN for a field that overflowed"""
    name = line[4:_NAME_END].strip()
    values = []
    for column in range(count):
        start = _NAME_END + column * _FIELD_WIDTH
        field = line[start : start + _FIELD_WIDTH].strip()
        try:
            values.append(float(field))
        except ValueError:
            values.append(np.nan)
    return name, values
