import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    compute_budget_overturning,
    get_budget_lines,
)

DC = 1000.0
LEVELS = 3


@pytest.fixture(scope='module')
def ds_init():
    """A channel closed in x, as an initial condition in the protocol's
    coordinates, with three layers in every column"""
    ds = make_planar_hex_mesh(
        nx=8, ny=6, dc=DC, nonperiodic_x=False, nonperiodic_y=False
    )
    x_period = ds.attrs['x_period']
    cells_on_edge = ds.cellsOnEdge.values.copy()
    x_cell = ds.xCell.values
    x1 = x_cell[cells_on_edge[:, 0] - 1]
    x2 = x_cell[cells_on_edge[:, 1] - 1]
    cells_on_edge[np.abs(x2 - x1) > 0.5 * x_period, 1] = 0
    ds['cellsOnEdge'] = (ds.cellsOnEdge.dims, cells_on_edge)
    ds.attrs['x_period'] = 0.0
    for location in ['Cell', 'Vertex']:
        for coord in ['x', 'y']:
            ds[f'{coord}Isomip{location}'] = ds[f'{coord}{location}']
    n_cells = ds.sizes['nCells']
    ds['minLevelCell'] = ('nCells', np.ones(n_cells, dtype=int))
    ds['maxLevelCell'] = ('nCells', LEVELS * np.ones(n_cells, dtype=int))
    ds['layerThickness'] = xr.ones_like(ds.xCell) * xr.DataArray(
        [10.0, 20.0, 30.0], dims='nVertLevels'
    )
    return ds


def _month(ds_init, rng, start='0001-01-01_00:00:00', end='0001-02-01'):
    """A month of means with a layer thickness flux on interior edges, and
    the snapshots of layer thickness it leads to"""
    n_edges = ds_init.sizes['nEdges']
    cells = ds_init.cellsOnEdge.values - 1
    interior = np.all(cells >= 0, axis=1)
    flux = rng.normal(size=(n_edges, LEVELS)) * interior[:, np.newaxis]
    transport = flux * ds_init.dvEdge.values[:, np.newaxis]
    gain = np.zeros((ds_init.sizes['nCells'], LEVELS))
    for edge in np.flatnonzero(interior):
        gain[cells[edge, 0]] -= transport[edge]
        gain[cells[edge, 1]] += transport[edge]
    duration = 31.0 * 86400.0
    thickness_start = ds_init.layerThickness
    thickness_end = (
        thickness_start
        + duration
        * xr.DataArray(gain, dims=('nCells', 'nVertLevels'))
        / ds_init.areaCell
    )
    ds = xr.Dataset()
    ds['xtime_startMonthly'] = ('Time', np.array([start.encode()]))
    ds['xtime_endMonthly'] = ('Time', np.array([f'{end}_00:00:00'.encode()]))
    ds['normalLayerThicknessFlux'] = (
        ('Time', 'nEdges', 'nVertLevels'),
        flux[np.newaxis],
    )
    ds['vertAleTransportTop'] = (
        ('Time', 'nCells', 'nVertLevelsP1'),
        np.zeros((1, ds_init.sizes['nCells'], LEVELS + 1)),
    )
    ds['landIceFreshwaterFlux'] = xr.zeros_like(ds_init.xCell).expand_dims(
        Time=1
    )
    ds['ssh'] = xr.zeros_like(ds_init.xCell).expand_dims(Time=1)
    ds['layerThickness'] = thickness_start.expand_dims(Time=1)
    return ds, thickness_start, thickness_end


def test_the_budget_agrees_with_the_layer_thickness_flux(ds_init):
    rng = np.random.default_rng(seed=3)
    ds, start, end = _month(ds_init, rng)
    x_lines = np.unique(ds_init.xCell.values)[1:-1] + 1.0
    snapshots = {0.0: start, 31.0: end}

    ds_osf = compute_budget_overturning(
        ds, ds_init, snapshots, x_lines, 1026.0
    )

    assert ds_osf.overturningBudget.dims == ('Time', 'x', 'nVertLevelsP1')
    np.testing.assert_allclose(
        ds_osf.overturningBudget.values,
        ds_osf.overturningLayerFlux.values,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        ds_osf.interfaceElevation.isel(Time=0, x=0).values,
        [0.0, -10.0, -30.0, -60.0],
    )


def test_the_initial_condition_stands_in_for_the_first_snapshot(ds_init):
    rng = np.random.default_rng(seed=3)
    ds, _, end = _month(ds_init, rng)
    x_lines = np.array([3.5 * DC])

    without = compute_budget_overturning(
        ds, ds_init, {31.0: end}, x_lines, 1026.0
    )
    with_initial = compute_budget_overturning(
        ds, ds_init, {31.0: end}, x_lines, 1026.0, initial_day=0.0
    )

    assert without is None
    np.testing.assert_allclose(
        with_initial.overturningBudget.values,
        with_initial.overturningLayerFlux.values,
        atol=1e-12,
    )


def test_without_the_vertical_transport_there_is_no_budget(ds_init):
    rng = np.random.default_rng(seed=3)
    ds, start, end = _month(ds_init, rng)
    ds = ds.drop_vars('vertAleTransportTop')
    snapshots = {0.0: start, 31.0: end}
    assert (
        compute_budget_overturning(
            ds, ds_init, snapshots, np.array([3.5 * DC]), 1026.0
        )
        is None
    )


def test_budget_lines_stop_at_the_restoring_region(ds_init):
    x_lines = get_budget_lines(ds_init, DC, restoring_x=4.0 * DC)
    assert x_lines.max() <= 4.0 * DC
    np.testing.assert_allclose(np.diff(x_lines), DC)
