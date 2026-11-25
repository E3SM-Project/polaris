import netCDF4
import numpy as np
import xarray as xr

from polaris.tasks.e3sm.analysis.misomip.wet_dry import (
    DRY,
    GROUNDED,
    IN_BETWEEN,
    WET,
    WETTING_FLAG,
    classify_cells,
    get_wet_dry_caption,
    read_wet_dry_states,
)

# three cells in a row: edge 1 joins cells 1 and 2, edge 2 cells 2 and 3,
# and edge 3 is on the boundary of cell 3
CELLS_ON_EDGE = np.array([[1, 2], [2, 3], [3, 0]])
EDGES_ON_CELL = np.array([[1, 0], [1, 2], [2, 3]])
N_EDGES_ON_CELL = np.array([1, 2, 2])


def _classify(open_fraction, grounded=(False, False, False)):
    return list(
        classify_cells(
            np.array(open_fraction),
            CELLS_ON_EDGE,
            EDGES_ON_CELL,
            N_EDGES_ON_CELL,
            np.array(grounded),
        )
    )


def test_cells_are_classified_by_their_active_edges():
    """A cell is dry when every active edge is closed, wet when none is,
    and the boundary edge counts for neither"""
    assert _classify([0.0, 1.0, 0.0]) == [DRY, IN_BETWEEN, WET]
    # an edge closed for part of the month
    assert _classify([1.0, 0.5, 1.0]) == [WET, IN_BETWEEN, IN_BETWEEN]
    # grounded wins over the flags
    assert _classify([0.0, 1.0, 0.0], (True, False, False)) == [
        GROUNDED,
        IN_BETWEEN,
        WET,
    ]


def _ds_init():
    return xr.Dataset(
        dict(
            cellsOnEdge=(('nEdges', 'TWO'), CELLS_ON_EDGE),
            edgesOnCell=(('nCells', 'maxEdges'), EDGES_ON_CELL),
            nEdgesOnCell=(('nCells',), N_EDGES_ON_CELL),
        )
    )


def _write(path, xtimes, variables):
    """A netCDF file with MPAS character times and per-record fields"""
    with netCDF4.Dataset(path, 'w') as nc:
        nc.createDimension('Time', None)
        nc.createDimension('StrLen', 64)
        nc.createDimension('nCells', 3)
        nc.createDimension('nEdges', 3)
        for name, values in xtimes.items():
            var = nc.createVariable(name, 'S1', ('Time', 'StrLen'))
            var._Encoding = 'ascii'
            var[:] = np.array(values, dtype='S64')
        for name, (dim, values) in variables.items():
            var = nc.createVariable(name, 'f8', ('Time', dim))
            var[:, :] = np.atleast_2d(values)
    return str(path)


def _restart(tmp_path, year, open_flag, floating):
    return _write(
        tmp_path / f'run.mpaso.rst.{year:04d}-01-01_00000.nc',
        dict(xtime=[f'{year:04d}-01-01_00:00:00']),
        {
            WETTING_FLAG: ('nEdges', open_flag),
            'landIceMask': ('nCells', [1, 1, 0]),
            'landIceFloatingMask': ('nCells', floating),
        },
    )


def _monthly(tmp_path, year, month, open_fraction):
    # the mean starts after the month's first time step, as MPAS-Ocean
    # writes it
    return _write(
        tmp_path / f'run.mpaso.hist.am.monthly.{year:04d}-{month:02d}-01.nc',
        dict(xtime_startMonthly=[f'{year:04d}-{month:02d}-01_00:01:00']),
        {f'timeMonthly_avg_{WETTING_FLAG}': ('nEdges', open_fraction)},
    )


def _snapshot(tmp_path, year, month, floating):
    return _write(
        tmp_path / f'run.mpaso.hist.am.snapshot.{year:04d}-{month:02d}-01.nc',
        dict(xtime=[f'{year:04d}-{month:02d}-01_00:00:00']),
        {
            'landIceMask': ('nCells', [1, 1, 0]),
            'landIceFloatingMask': ('nCells', floating),
        },
    )


def test_year_start_snapshots_hold_until_the_monthly_means(tmp_path):
    """The restarts give a state each year until the monthly means have
    the flag; a restart at or after the first month is left out, but its
    masks ground the first month"""
    restarts = [
        _restart(tmp_path, 2, [0.0, 1.0, 1.0], [0, 1, 0]),
        _restart(tmp_path, 3, [1.0, 1.0, 1.0], [1, 1, 0]),
    ]
    without_flag = _write(
        tmp_path / 'run.mpaso.hist.am.monthly.0002-12-01.nc',
        dict(xtime_startMonthly=['0002-12-01_00:00:00']),
        {},
    )
    monthly = [without_flag, _monthly(tmp_path, 3, 1, [0.0, 0.5, 1.0])]
    states = read_wet_dry_states(_ds_init(), restarts, monthly, [])
    assert states.labels == [
        'year-start snapshot, 0002-01-01',
        'monthly, 0003-01',
    ]
    np.testing.assert_allclose(states.start_days, [365.0, 730.0])
    assert list(states.classes[0]) == [GROUNDED, IN_BETWEEN, WET]
    # nothing is grounded at the start of year 3, so the first cell is dry
    assert list(states.classes[1]) == [DRY, IN_BETWEEN, IN_BETWEEN]
    # each state holds until the next, and there is none before the first
    assert states.state_at(364.0) is None
    assert states.state_at(400.0) == 0
    assert states.state_at(760.0) == 1
    caption = get_wet_dry_caption(states)
    assert 'start of each year' in caption
    assert 'each month' in caption
    assert 'start of the month' in caption


def test_monthly_masks_come_from_the_month_start_snapshot(tmp_path):
    """The snapshot at the start of a month grounds it; without one, the
    monthly states stop"""
    monthly = [
        _monthly(tmp_path, 3, 2, [0.0, 1.0, 1.0]),
        _monthly(tmp_path, 3, 3, [0.0, 1.0, 1.0]),
    ]
    snapshot = _snapshot(tmp_path, 3, 2, [0, 1, 0])
    states = read_wet_dry_states(_ds_init(), [], monthly, [snapshot])
    assert states.labels == ['monthly, 0003-02']
    caption = get_wet_dry_caption(states)
    assert 'start of each year' not in caption
    assert 'each month' in caption
    assert list(states.classes[0]) == [GROUNDED, IN_BETWEEN, WET]
    assert read_wet_dry_states(_ds_init(), [], [], []) is None


def test_caption_has_no_monthly_clause_without_monthly_frames(tmp_path):
    """A page with only year-start frames says nothing of monthly ones"""
    restarts = [_restart(tmp_path, 2, [0.0, 1.0, 1.0], [0, 1, 0])]
    states = read_wet_dry_states(_ds_init(), restarts, [], [])
    caption = get_wet_dry_caption(states)
    assert 'start of each year' in caption
    assert 'month' not in caption
