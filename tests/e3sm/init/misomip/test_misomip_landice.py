import netCDF4
import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.misomip.calving import (
    calve,
    get_floating_mask,
    get_grounded_mask,
)
from polaris.tasks.e3sm.init.misomip.land_ice_fields import (
    GRAVITY,
    apply_map,
    compute_mali_export,
    import_geometry,
    read_map,
)
from polaris.tasks.e3sm.init.misomip.landice_data import (
    write_data_mode_file,
)
from polaris.tasks.e3sm.init.misomip.landice_init import (
    get_landice_thickness,
    remap_input_thickness,
)
from polaris.tasks.e3sm.init.misomip.records import (
    SECONDS_PER_DAY,
    get_interpolation_weights,
    get_monthly_record_times,
)


def test_floating_and_grounded_masks():
    # densities whose ratio is exact, so 1800 m of ice is exactly at
    # flotation on a bed 900 m deep
    densities = dict(ice_density=500.0, ocean_density=1000.0)
    bed = np.array([-900.0, -900.0, -900.0, -900.0, 100.0])
    thickness = np.array([0.0, 500.0, 1800.0, 2000.0, 50.0])
    floating = get_floating_mask(thickness, bed, **densities)
    grounded = get_grounded_mask(thickness, bed, **densities)
    # ice exactly at flotation floats, as in MALI
    np.testing.assert_array_equal(floating, [False, True, True, False, False])
    np.testing.assert_array_equal(grounded, [False, False, False, True, True])


def test_calve_thin_floating_ice():
    bed = np.array([-900.0, -900.0, -50.0, -900.0, -900.0])
    thickness = np.array([99.0, 100.0, 99.0, 500.0, 500.0])
    x_cell = np.array([500.0e3, 500.0e3, 500.0e3, 640.0e3, 641.0e3])
    calved = calve(thickness, bed, x_cell)
    # thin floating ice and any ice beyond 640 km go; thin grounded ice and
    # ice at 100 m stay
    np.testing.assert_array_equal(calved, [0.0, 100.0, 99.0, 500.0, 0.0])


def test_calve_with_time_records():
    bed = np.array([-900.0, -900.0])
    thickness = np.array([[50.0, 500.0], [500.0, 50.0]])
    x_cell = np.array([400.0e3, 400.0e3])
    calved = calve(thickness, bed, x_cell)
    np.testing.assert_array_equal(calved, [[0.0, 500.0], [500.0, 0.0]])


def test_monthly_record_times():
    xtimes, seconds = get_monthly_record_times(year_count=100)
    assert len(xtimes) == 1201
    assert xtimes[0] == '0001-01-01_00:00:00'
    assert xtimes[1] == '0001-02-01_00:00:00'
    assert xtimes[12] == '0002-01-01_00:00:00'
    assert xtimes[-1] == '0101-01-01_00:00:00'
    assert seconds[0] == 0.0
    assert seconds[1] == 31.0 * SECONDS_PER_DAY
    assert seconds[12] == 365.0 * SECONDS_PER_DAY
    # the protocol's last yearly record, in seconds
    assert seconds[-1] == 3153600000.0
    assert np.all(np.diff(seconds) > 0.0)


def test_interpolation_weights():
    yearly = 365.0 * SECONDS_PER_DAY * np.arange(101)
    _, seconds = get_monthly_record_times(year_count=100)
    before, after, weight = get_interpolation_weights(seconds, yearly)

    # the start of each year is a yearly record
    np.testing.assert_array_equal(before[::12], np.arange(101).clip(max=99))
    np.testing.assert_allclose(weight[:-1:12], 0.0)
    assert weight[-1] == 1.0
    assert after[-1] == 100

    # the start of February is 31 days into the first year
    assert before[1] == 0
    assert after[1] == 1
    assert weight[1] == pytest.approx(31.0 / 365.0)

    assert np.all(weight >= 0.0)
    assert np.all(weight <= 1.0)


def test_interpolation_weights_outside_the_records():
    with pytest.raises(ValueError):
        get_interpolation_weights(np.array([2.0]), np.array([0.0, 1.0]))


def _synthetic_map(tmp_path):
    """
    A map from 4 MALI cells to 3 ocean cells: the first ocean cell is
    covered by halves of MALI cells 0 and 1, the second by quarters of
    MALI cells 2 and 3, and the third by no MALI cell
    """
    ds = xr.Dataset()
    ds['S'] = ('n_s', np.array([0.5, 0.5, 0.25, 0.25]))
    ds['row'] = ('n_s', np.array([1, 1, 2, 2], dtype=np.int32))
    ds['col'] = ('n_s', np.array([1, 2, 3, 4], dtype=np.int32))
    ds['area_a'] = ('n_a', np.ones(4))
    ds['area_b'] = ('n_b', np.ones(3))
    filename = str(tmp_path / 'map.nc')
    ds.to_netcdf(filename)
    return filename


def test_mali_export():
    bed = np.array([-900.0, -900.0, -900.0, 100.0])
    thickness = np.array([0.0, 500.0, 1100.0, 50.0])
    export = compute_mali_export(thickness, bed)
    rho_g = 918.0 * GRAVITY
    np.testing.assert_array_equal(
        export['below_sea_level_mask'], [1.0, 1.0, 1.0, 0.0]
    )
    np.testing.assert_allclose(
        export['lithop'], [0.0, 500.0 * rho_g, 1100.0 * rho_g, 0.0]
    )
    np.testing.assert_array_equal(
        export['icemask_floating'], [0.0, 1.0, 0.0, 0.0]
    )
    # grounded ice above sea level is not exported
    np.testing.assert_array_equal(
        export['icemask_grounded'], [0.0, 0.0, 1.0, 0.0]
    )
    assert GRAVITY == 9.80616


def test_land_ice_fields_through_a_map(tmp_path):
    bed = np.array([-900.0, -900.0, -900.0, 100.0])
    thickness = np.array([0.0, 500.0, 1100.0, 50.0])
    matrix = read_map(_synthetic_map(tmp_path))
    assert matrix.shape == (3, 4)

    export = compute_mali_export(thickness, bed)
    mapped = {name: apply_map(matrix, export[name]) for name in export}
    fields = import_geometry(mapped)

    rho_g = 918.0 * GRAVITY
    np.testing.assert_allclose(
        fields['landIcePressure'], [250.0 * rho_g, 1100.0 * rho_g, 0.0]
    )
    np.testing.assert_allclose(
        fields['landIceFloatingFraction'], [0.5, 0.0, 0.0]
    )
    # normalized by the part of the cell below sea level in MALI
    np.testing.assert_allclose(fields['landIceFraction'], [0.5, 1.0, 0.0])
    np.testing.assert_allclose(
        fields['landIceGroundedFraction'], [0.0, 1.0, 0.0]
    )


def test_land_ice_fields_with_time_records(tmp_path):
    bed = np.array([-900.0, -900.0, -900.0, 100.0])
    thickness = np.array(
        [[0.0, 500.0, 1100.0, 50.0], [500.0, 500.0, 1100.0, 50.0]]
    )
    matrix = read_map(_synthetic_map(tmp_path))
    export = compute_mali_export(thickness, bed)
    mapped = {name: apply_map(matrix, export[name]) for name in export}
    fields = import_geometry(mapped)
    assert fields['landIcePressure'].shape == (2, 3)
    np.testing.assert_allclose(
        fields['landIceFloatingFraction'], [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0]]
    )


def _synthetic_input(thickness_records):
    """
    ISOMIP+-like input geometry on a grid of 1 by 2 cells, with columns
    centered at x = 320.5 and 321.5 km
    """
    thickness = np.asarray(thickness_records, dtype=float)
    ds = xr.Dataset()
    ds['x'] = ('x', np.array([320.5e3, 321.5e3]))
    ds['y'] = ('y', np.array([0.5e3]))
    ds['upperSurface'] = (('t', 'y', 'x'), 0.1 * thickness[:, np.newaxis, :])
    ds['lowerSurface'] = (
        ('t', 'y', 'x'),
        -0.9 * thickness[:, np.newaxis, :],
    )
    return ds


def _synthetic_input_map(tmp_path):
    """
    A map from the 2 input cells to 3 MALI cells: the first covered by the
    first input cell, the second half covered by the second, the third not
    at all
    """
    ds = xr.Dataset()
    ds['S'] = ('n_s', np.array([1.0, 0.5]))
    ds['row'] = ('n_s', np.array([1, 2], dtype=np.int32))
    ds['col'] = ('n_s', np.array([1, 2], dtype=np.int32))
    ds['area_a'] = ('n_a', np.ones(2))
    ds['area_b'] = ('n_b', np.ones(3))
    filename = str(tmp_path / 'input_map.nc')
    ds.to_netcdf(filename)
    return filename


def test_remap_input_thickness(tmp_path):
    ds_input = _synthetic_input([[300.0, 600.0], [200.0, 400.0]])
    remapped = remap_input_thickness(ds_input, _synthetic_input_map(tmp_path))
    # the mean over the part of each cell the input covers
    np.testing.assert_allclose(
        remapped, [[300.0, 600.0, 0.0], [200.0, 400.0, 0.0]]
    )


def test_landice_thickness_from_input(tmp_path):
    ds_input = _synthetic_input([[300.0, 50.0]])
    map_filename = _synthetic_input_map(tmp_path)
    # the third cell is upstream of the input, so it keeps the steady state
    x_cell = np.array([330.0e3, 340.0e3, 310.0e3])
    bed = np.array([-900.0, -900.0, -900.0])
    steady_thickness = np.array([1000.0, 1000.0, 1500.0])
    thickness = get_landice_thickness(
        ds_input=ds_input,
        map_filename=map_filename,
        steady_thickness=steady_thickness,
        bed_topography=bed,
        x_cell=x_cell,
    )
    # floating ice thinner than 100 m is calved
    np.testing.assert_allclose(thickness, [[300.0, 0.0, 1500.0]])


def test_write_data_mode_file(tmp_path):
    filename = str(tmp_path / 'datamode.nc')
    xtimes = ['0001-01-01_00:00:00', '0001-02-01_00:00:00']
    write_data_mode_file(
        filename=filename,
        xtimes=xtimes,
        get_thickness=lambda index: np.full(4, 10.0 * (index + 1)),
    )
    with netCDF4.Dataset(filename) as ds:
        thickness = ds.variables['thickness'][:]
        xtime = netCDF4.chartostring(ds.variables['xtime'][:])
    np.testing.assert_allclose(thickness, [[10.0] * 4, [20.0] * 4])
    assert [value.strip() for value in xtime] == xtimes
