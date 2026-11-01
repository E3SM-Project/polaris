import gzip

import numpy as np
import pytest
from mpas_tools.cime.constants import constants

from polaris.e3sm.analysis.budgets import (
    budget_time_series,
    read_budget_tables,
    read_initial_start,
)

COMPONENTS = [
    '     atm',
    '     lnd',
    '     rof',
    '     ocn',
    '  ice nh',
    '  ice sh',
    '     glc',
    ' *SUM*  ',
]


def _header_line(budget, units, period, date, seconds):
    """The coupler's FAH format: (4a,i9,i6), with the period's name
    right-justified in 8 characters, as the coupler's names are"""
    return (
        f'(seq_diag_print_mct) NET {budget} BUDGET ({units}): period = '
        f'{period:>8}: date = {date:9d}{seconds:6d}'
    )


def _component_line():
    """The coupler's FA0r format: ('    ',12x,8(6x,a8,1x))"""
    fields = ''.join(f'{" " * 6}{name} ' for name in COMPONENTS)
    return '    ' + ' ' * 12 + fields


def _row_line(name, values):
    """The coupler's FA1r format: ('    ',a12,8f15.8), with Fortran's
    asterisks for a value too wide for its field"""
    fields = []
    for value in values:
        field = f'{value:15.8f}'
        fields.append('*' * 15 if len(field) > 15 else field)
    return f'    {name:>12}' + ''.join(fields)


def _water_table(date, ocean, glc):
    """A monthly water budget whose ocean and glc columns exchange the
    melt"""
    lines = [
        ' ',
        _header_line('WATER', 'kg/m2s*1e6', 'monthly', date, 0),
        _component_line(),
    ]
    for name in ['wfreeze', 'wpolar']:
        values = [0.0] * 8
        if name == 'wpolar':
            values[3] = ocean
            values[6] = glc
            values[7] = ocean + glc
        lines.append(_row_line(name, values))
    lines.append(' ')
    return lines


def _write_log(filename, lines, compress=False):
    text = '\n'.join(lines) + '\n'
    if compress:
        with gzip.open(filename, 'wt') as log:
            log.write(text)
    else:
        with open(filename, 'w') as log:
            log.write(text)


def test_budget_tables_are_read_by_position(tmp_path):
    """A value that fills its whole field touches the one before it, and an
    overflowed field is NaN."""
    lines = [
        _header_line('HEAT', 'W/m2', 'annual', 20101, 0),
        _component_line(),
        _row_line('hpolar', [0.0, 0.0, 0.0, -12345.12345678] + [0.0] * 4),
        _row_line('*SUM*', [1.0e9] + [0.0] * 7),
        ' ',
    ]
    filename = str(tmp_path / 'cpl.log')
    _write_log(filename, lines)

    (table,) = read_budget_tables([filename])

    assert (table.budget, table.period) == ('HEAT', 'annual')
    assert (table.year, table.month, table.day) == (2, 1, 1)
    assert table.components == [name.strip() for name in COMPONENTS]
    assert table.rows == ['hpolar', '*SUM*']
    assert table.values[0, 3] == -12345.12345678
    assert np.isnan(table.values[1, 0])


def test_a_water_budget_becomes_a_time_series_of_totals(tmp_path):
    """Two monthly tables in two logs, one compressed, with the second log
    repeating the first month as a restarted run does."""
    first = str(tmp_path / 'cpl.log.1.gz')
    second = str(tmp_path / 'cpl.log.2')
    _write_log(
        first,
        _water_table(10201, 0.003, -0.002) + ['other output'],
        compress=True,
    )
    _write_log(
        second,
        _water_table(10201, 0.003, -0.003)
        + _water_table(10301, 0.004, -0.004),
    )

    tables = read_budget_tables([first, second])
    ds = budget_time_series(tables, 'WATER', 'monthly')

    assert list(ds.date.values) == ['0001-02-01_00000', '0001-03-01_00000']
    polar = ds.budget.sel(row='wpolar')
    sphere = 4.0 * np.pi * constants['SHR_CONST_REARTH'] ** 2
    np.testing.assert_allclose(
        polar.sel(component='ocn').values,
        1.0e-6 * sphere * np.array([0.003, 0.004]),
    )
    # the restarted month is the later log's, which closes
    np.testing.assert_allclose(polar.sel(component='*SUM*').values, 0.0)
    assert ds.budget.attrs['units'] == 'kg s-1'


def test_a_missing_budget_asks_whether_budgets_were_on(tmp_path):
    filename = str(tmp_path / 'cpl.log')
    _write_log(filename, _water_table(10201, 0.003, -0.003))
    tables = read_budget_tables([filename])

    with pytest.raises(ValueError, match='BUDGETS=TRUE'):
        budget_time_series(tables, 'HEAT', 'monthly')


def _driver_lines(skip):
    """The driver's start date and whether it skipped the ocean's first
    coupling interval, padded as the driver writes them"""
    return [
        '(seq_timemgr_clockInit) start_ymd      =      10101',
        '(seq_timemgr_clockInit) start_tod      =          0',
        f'(cpl7mct_driver) : skip init ocean run   =      {skip}',
    ]


def test_the_initial_start_is_found_in_its_log(tmp_path):
    """A run started in one log and continued in another: only the first
    skipped the ocean's first coupling interval."""
    first = str(tmp_path / 'cpl.log.1')
    second = str(tmp_path / 'cpl.log.2.gz')
    _write_log(first, _driver_lines('T') + _water_table(10201, 0.003, -0.002))
    _write_log(
        second,
        _driver_lines('F') + _water_table(10301, 0.003, -0.003),
        compress=True,
    )

    assert read_initial_start([first, second]) == '0001-01-01_00000'
    assert read_initial_start([second]) is None
