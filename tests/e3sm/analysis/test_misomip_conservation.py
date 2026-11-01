import numpy as np
import xarray as xr

from polaris.e3sm.analysis.budgets import BudgetTable
from polaris.tasks.e3sm.analysis.misomip.conservation import (
    _end_years,
    _ends_in_period,
    _ocean_series,
)


def test_the_ocean_s_months_line_up_with_the_budgets_that_cover_them():
    """Monthly budgets are dated at the end of their months: the one dated
    0001-02-01 covers January.  The ocean's series has January and
    February; the budget for December of year 1 has no month and is NaN."""
    ds_ocean = xr.Dataset()
    ds_ocean['totalMeltFlux'] = ('Time', [4.0, 5.0])
    ds_ocean['totalFrazilFlux'] = ('Time', [-1.0, -2.0])
    # the middle of each month, in model years
    ds_ocean.coords['time'] = ('Time', [1.0 + 0.5 / 12.0, 1.0 + 1.5 / 12.0])
    dates = ['0001-02-01_00000', '0001-03-01_00000', '0002-01-01_00000']

    ocean = _ocean_series(ds_ocean, dates, scale=2.0)

    np.testing.assert_allclose(ocean['totalMeltFlux'], [8.0, 10.0, np.nan])
    np.testing.assert_allclose(ocean['totalFrazilFlux'], [-2.0, -4.0, np.nan])
    np.testing.assert_allclose(ocean['meltPlusFrazil'], [6.0, 6.0, np.nan])


def test_budgets_are_placed_at_the_end_of_their_periods():
    """A daily budget at noon on 2 January, the January budget dated
    1 February, and the year's budget dated 1 January of year 2, in model
    years."""
    years = _end_years(
        ['0001-01-02_43200', '0001-02-01_00000', '0002-01-01_00000']
    )

    np.testing.assert_allclose(
        years, [1.0 + 1.5 / 365.0, 1.0 + 31.0 / 365.0, 2.0]
    )


def test_only_the_budgets_that_end_in_the_period_are_checked():
    """Years 1-10 hold the budgets for January of year 1, dated 1 February,
    through December of year 10, dated 1 January of year 11; a segment's
    log also holds year 11's"""
    dates = [(1, 2, 1), (11, 1, 1), (11, 2, 1)]
    tables = [
        BudgetTable(
            'WATER', 'monthly', year, month, day, 0, '', [], [], np.zeros(0)
        )
        for year, month, day in dates
    ]

    kept = [_ends_in_period(table, 0.0, 3650.0) for table in tables]

    assert kept == [True, True, False]
