import numpy as np
import xarray as xr

from polaris.analysis.page import Page
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    _assemble_run_health,
)
from polaris.tasks.e3sm.analysis.misomip.health import (
    MPAS_GRAVITY,
    compute_dry_cells,
    compute_salt_excess,
    compute_spike_cells,
    get_source_max_salinity,
)
from polaris.tasks.e3sm.analysis.misomip.health_page import (
    add_health_sections,
)


def _mesh():
    """Four cells along x: grounded-line neighbor, shelf, front, open"""
    ds = xr.Dataset()
    ds['xIsomipCell'] = ('nCells', [450e3, 470e3, 600e3, 700e3])
    ds['yIsomipCell'] = ('nCells', np.full(4, 40e3))
    ds['areaCell'] = ('nCells', np.full(4, 4e6))
    ds['salinity'] = (('nCells', 'nVertLevels'), np.full((4, 2), 34.5))
    ds['layerThickness'] = (('nCells', 'nVertLevels'), np.full((4, 2), 10.0))
    return ds


def test_the_source_maximum_leaves_out_unrestored_and_fill_values():
    ds_init = _mesh()
    ds_init['salinity'][0, 0] = 40.0
    ds_init['layerThickness'][0, 0] = 0.0
    ds_restoring = xr.Dataset()
    ds_restoring['salinityInteriorRestoringValue'] = (
        'nCells',
        [34.7, 35.0, 9.96921e36, 34.6],
    )
    ds_restoring['salinityInteriorRestoringRate'] = (
        'nCells',
        [1e-6, 0.0, 1e-6, 1e-6],
    )
    assert get_source_max_salinity(ds_init) == 34.5
    assert get_source_max_salinity(ds_init, ds_restoring) == 34.7


def test_a_spike_is_a_cell_faster_than_the_threshold_on_a_day():
    kinetic_energy = xr.DataArray(
        np.zeros((2, 4, 2)), dims=('Time', 'nCells', 'nVertLevels')
    )
    # 4 m/s in cell 2 on the second day, and 2 m/s in cell 1
    kinetic_energy[1, 2, 1] = 8.0
    kinetic_energy[1, 1, 0] = 2.0
    ds = compute_spike_cells(kinetic_energy, [365.0, 366.0], 3.0, _mesh())
    assert ds.spikeDay.values.tolist() == [366.0]
    assert ds.spikeCell.values.tolist() == [2]
    np.testing.assert_allclose(ds.spikeSpeed, [4.0])
    np.testing.assert_allclose(ds.spikeX, [600.0])


def test_a_run_without_spikes_has_no_spike_dimension():
    """A dimension of size zero would be unlimited in the file"""
    no_spikes = compute_spike_cells(
        xr.DataArray(
            np.zeros((1, 4, 2)), dims=('Time', 'nCells', 'nVertLevels')
        ),
        [0.0],
        3.0,
        _mesh(),
    )
    salt = xr.Dataset({'saltyCells': ('Time', [0])})
    ds = _assemble_run_health([{'spikes': no_spikes, 'salt_excess': salt}])
    assert 'nSpikes' not in ds.dims


def test_excess_salt_is_split_into_three_regions():
    """Near the grounding line, under the rest of the shelf, and beyond
    the front"""
    ds_init = _mesh()
    ds = xr.Dataset()
    ds['salinity'] = (
        ('Time', 'nCells', 'nVertLevels'),
        np.full((1, 4, 2), 34.5),
    )
    ds['layerThickness'] = (
        ('Time', 'nCells', 'nVertLevels'),
        np.full((1, 4, 2), 10.0),
    )
    # cell 0 partly floats; cells 1 and 2 float
    ds['landIceFloatingFraction'] = (
        ('Time', 'nCells'),
        [[0.5, 1.0, 1.0, 0.0]],
    )
    # 1 PSU over 10 m in one layer of each cell but cell 1
    for cell in [0, 2, 3]:
        ds['salinity'][0, cell, 0] = 35.5
    ds_out = compute_salt_excess(ds, ds_init, 34.5, 10e3, 640e3)
    # 1 PSU * 10 m * 4 km2 = 0.04 PSU km3
    np.testing.assert_allclose(ds_out.saltExcessNearGroundingLine, [0.04])
    np.testing.assert_allclose(ds_out.saltExcessUnderShelf, [0.04])
    np.testing.assert_allclose(ds_out.saltExcessBeyondFront, [0.04])
    np.testing.assert_allclose(ds_out.maxSalinityExcess, [1.0])
    assert ds_out.saltyCells.values.tolist() == [3]


def test_a_dry_column_s_deficit_is_the_column_its_ice_calls_for():
    ds_init = _mesh()
    ds_init['bottomDepth'] = ('nCells', np.full(4, 100.0))
    ds_init['minLevelCell'] = ('nCells', np.ones(4, dtype=int))
    ds_init['maxLevelCell'] = ('nCells', np.full(4, 2))
    density = 1028.0
    gravity = MPAS_GRAVITY
    state = xr.Dataset()
    # cells 0 and 1 are dry; the ice over cell 0 calls for a 7 m column
    state['layerThickness'] = (
        ('nCells', 'nVertLevels'),
        [[0.05, 0.05], [0.05, 0.054], [10.0, 0.05], [10.0, 10.0]],
    )
    state['landIcePressure'] = (
        'nCells',
        [93.0 * density * gravity, 100.0 * density * gravity, 0.0, 0.0],
    )
    ds = compute_dry_cells(state, ds_init, 0.05, density)
    assert int(ds.dryCells) == 2
    assert ds.dryCellsWithDeficit.values.tolist() == [1, 1, 0]
    np.testing.assert_allclose(ds.maxDryDeficit, 6.9)
    assert ds.largestDeficitCell.values.tolist() == [0, -1, -1, -1, -1]
    np.testing.assert_allclose(ds.largestDeficitX[0], 450.0)


def test_the_page_has_a_table_for_each_check():
    ds = xr.Dataset()
    ds['spikeDay'] = ('nSpikes', [400.0, 400.0])
    ds['spikeCell'] = ('nSpikes', [3, 5])
    ds['spikeX'] = ('nSpikes', [500.0, 502.0])
    ds['spikeY'] = ('nSpikes', [40.0, 42.0])
    ds['spikeSpeed'] = ('nSpikes', [3.5, 4.5])
    ds = ds.assign_coords(time=('Time', [1.5 / 12.0 + 1.0, 2.0 + 0.5 / 12]))
    for name in [
        'maxSalinityExcess',
        'saltyCells',
        'saltExcessNearGroundingLine',
        'saltExcessUnderShelf',
        'saltExcessBeyondFront',
    ]:
        ds[name] = ('Time', [0.0, 0.1])
    ds.coords['deficitThreshold'] = ('nDeficitThresholds', [1.0, 5.0, 10.0])
    ds['dryTime'] = ('nDryStates', [0.0, 365.0])
    ds['dryCells'] = ('nDryStates', [0, 2])
    ds['dryCellsWithDeficit'] = (
        ('nDryStates', 'nDeficitThresholds'),
        [[0, 0, 0], [1, 0, 0]],
    )
    ds['maxDryDeficit'] = ('nDryStates', [np.nan, 1.5])
    ds['largestDeficitCell'] = (
        ('nDryStates', 'nLargestDeficits'),
        [[-1, -1], [7, -1]],
    )
    for name, value in [('X', 600.0), ('Y', 40.0), ('', 1.5)]:
        ds[f'largestDeficit{name}'] = (
            ('nDryStates', 'nLargestDeficits'),
            [[np.nan, np.nan], [value, np.nan]],
        )
    ds.attrs.update(
        source_max_salinity=34.688,
        spike_speed=3.0,
        salt_near_distance=10000.0,
        ice_front_x=640000.0,
        min_thickness=0.05,
        land_ice_ocean_density=1028.0,
        has_custom=1,
    )
    page = Page('e3sm_run_health', 'Health of the E3SM run')
    add_health_sections(page, ds)
    spikes, salt, dry = page.sections
    assert [cell['value'] for cell in spikes['table']['rows'][0]] == [
        '0002-02-05',
        '4.50',
        '2',
        '5 (502.0, 42.0) 4.50 m/s; 3 (500.0, 40.0) 3.50 m/s',
    ]
    assert [row[0]['value'] for row in salt['table']['rows']] == [
        '0001',
        '0002',
    ]
    assert [cell['value'] for cell in dry['table']['rows'][1]] == [
        '0002-01-01',
        '2',
        '1',
        '0',
        '0',
        '1.50',
        '7 (600.0, 40.0) 1.50 m',
    ]
