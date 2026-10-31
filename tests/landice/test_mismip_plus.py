import logging
import os

import netCDF4
import numpy as np
import pytest
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.config import PolarisConfigParser
from polaris.landice.mesh import make_mali_mesh
from polaris.landice.mismip_plus.diagnostics import compute_diagnostics
from polaris.landice.mismip_plus.geometry import (
    ICE_DENSITY,
    MALI_SECONDS_PER_YEAR,
    OCEAN_DENSITY,
    SECONDS_PER_YEAR,
    bed_topography,
)
from polaris.landice.mismip_plus.mesh import (
    get_mesh_parameters,
    make_mismip_plus_mesh,
)
from polaris.tasks.landice import Landice
from polaris.tasks.landice.add_tasks import add_landice_tasks
from polaris.tasks.landice.mismip_plus.cornford import (
    _centerline_position,
    _gather_entries,
)
from polaris.tasks.landice.mismip_plus.forward import (
    MALI_LATENT_HEAT,
    _get_melt_options,
    _write_starting_state,
)
from polaris.tasks.landice.mismip_plus.init import _add_mismip_plus_fields
from polaris.tasks.landice.mismip_plus.output import read_output
from polaris.tasks.landice.mismip_plus.plot import (
    GLOBAL_STATS_FLUX,
    GLOBAL_STATS_VOLUME,
    plot_global_stats,
)
from polaris.tasks.landice.mismip_plus.spin_up.run import get_restart_year
from polaris.tasks.landice.mismip_plus.steps import (
    get_mismip_plus_steady_state_steps,
)

EXPERIMENTS = [
    'ice0',
    'ice1r',
    'ice1ra',
    'ice1rr',
    'ice2r',
    'ice2ra',
    'ice2rr',
]


def test_bed_topography():
    y_center = 40.0e3
    # Eq. 2 at the divide and on the trough's floor, with the walls far away
    np.testing.assert_allclose(
        bed_topography(0.0, y_center), -150.0, atol=0.01
    )
    np.testing.assert_allclose(
        bed_topography(300.0e3, y_center),
        -150.0 - 728.8 + 343.91 - 50.57,
        atol=0.01,
    )
    # the bed is no deeper than 720 m
    assert bed_topography(640.0e3, y_center) == -720.0
    # the trough is symmetric about the centerline
    y = np.linspace(0.0, 80.0e3, 9)
    np.testing.assert_allclose(
        bed_topography(400.0e3, y), bed_topography(400.0e3, y[::-1])
    )


def test_mesh_parameters():
    nx, ny, dc = get_mesh_parameters(resolution=1.0)
    assert (nx, ny) == (653, 96)
    np.testing.assert_allclose(dc, 982.72386245)
    # one row is culled, leaving ny - 2 intervals across the domain
    np.testing.assert_allclose(0.5 * np.sqrt(3.0) * dc * (ny - 2), 80.0e3)


def test_make_mismip_plus_mesh():
    logger = logging.getLogger(__name__)
    ds = make_mismip_plus_mesh(resolution=8.0, logger=logger)
    nx, ny, dc = get_mesh_parameters(resolution=8.0)

    assert ds.sizes['nCells'] == nx * (ny - 1)
    np.testing.assert_allclose(ds.xCell.min(), 0.0, atol=1e-6)
    np.testing.assert_allclose(ds.yCell.min(), 0.0, atol=1e-6)
    np.testing.assert_allclose(ds.yCell.max(), 80.0e3)
    # the cells span the calving front plus a gutter
    assert ds.xCell.max() > 640.0e3 + dc

    y = ds.yCell.values
    wall = np.isclose(y, 0.0, atol=1.0) | np.isclose(y, 80.0e3, atol=1.0)
    area = ds.areaCell.values
    np.testing.assert_allclose(area[wall], 0.5 * area[~wall].max())
    np.testing.assert_allclose(area[~wall], area[~wall].max())


def test_compute_diagnostics():
    ds = _make_centerline_dataset(x_gl=4.0e3, x0=0.0)
    ds_diag = compute_diagnostics(ds)

    thickness = ds.thickness.values
    haf = thickness - OCEAN_DENSITY / ICE_DENSITY * 1000.0
    np.testing.assert_allclose(ds_diag.iceVolume, thickness.sum() * 2.0)
    np.testing.assert_allclose(ds_diag.iceVAF, haf[haf > 0.0].sum() * 2.0)
    np.testing.assert_allclose(ds_diag.groundedArea, 2.0 * (haf > 0.0).sum())
    # the thickness above flotation is zero 4 km along the centerline
    np.testing.assert_allclose(ds_diag.xGL, 4.0e3)

    # and the same with a time dimension
    ds_time = ds.copy()
    for var in ['thickness', 'bedTopography']:
        ds_time[var] = xr.concat([ds[var], ds[var]], dim='Time')
    ds_diag_time = compute_diagnostics(ds_time)
    assert ds_diag_time.xGL.dims == ('Time',)
    np.testing.assert_allclose(ds_diag_time.xGL, 4.0e3)


def test_add_mismip_plus_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logger = logging.getLogger(__name__)
    write_netcdf(
        make_mismip_plus_mesh(resolution=8.0, logger=logger), 'mesh.nc'
    )
    make_mali_mesh(
        in_filename='mesh.nc',
        out_filename='mali_mesh.nc',
        levels=3,
        logger=logger,
        thermal=True,
        dirichlet=True,
    )
    ds = xr.open_dataset('mali_mesh.nc').load()
    _add_mismip_plus_fields(ds)

    x = ds.xCell.values
    y = ds.yCell.values
    thickness = ds.thickness.isel(Time=0).values
    np.testing.assert_array_equal(thickness, np.where(x < 640.0e3, 100.0, 0.0))
    np.testing.assert_array_equal(
        ds.calvingMask.isel(Time=0).values, (x > 640.0e3).astype(int)
    )
    wall = np.isclose(y, 0.0, atol=1.0) | np.isclose(y, 80.0e3, atol=1.0)
    mask = ds.dirichletVelocityMask.isel(Time=0).values
    assert np.all(mask[wall, :] == 1)
    assert np.all(mask[~wall, :] == 0)
    # 0.3 m a^-1 of ice and the friction coefficient in MALI's units
    np.testing.assert_allclose(
        ds.sfcMassBal.values * SECONDS_PER_YEAR / ICE_DENSITY, 0.3
    )
    np.testing.assert_allclose(
        ds.muFriction.values * MALI_SECONDS_PER_YEAR ** (1.0 / 3.0), 3.160e6
    )
    np.testing.assert_allclose(ds.effectivePressure.values, 1.0)


def test_ice2_melt_rate():
    options = _get_melt_options('constant')
    melt_rate = (
        options['config_bmlt_float_flux']
        / (ICE_DENSITY * MALI_LATENT_HEAT)
        * SECONDS_PER_YEAR
    )
    np.testing.assert_allclose(melt_rate, 100.0)
    assert options['config_bmlt_float_xlimit'] == 480.0e3
    assert _get_melt_options('none') == {'config_basal_mass_bal_float': 'none'}
    with pytest.raises(ValueError, match='melt'):
        _get_melt_options('unknown')


def test_write_starting_state(tmp_path):
    # the steady state is MALI's restart at the end of the spin-up
    ds = xr.Dataset()
    ds['xtime'] = ('Time', np.array(['1000-01-01_00:00:00'], dtype='S64'))
    ds['thickness'] = (('Time', 'nCells'), np.ones((1, 3)))
    write_netcdf(ds, str(tmp_path / 'steady_state.nc'))

    out_filename = str(tmp_path / 'landice_grid.nc')
    _write_starting_state(str(tmp_path / 'steady_state.nc'), out_filename, 100)
    ds = read_output(out_filename)
    np.testing.assert_allclose(ds.Time, [100.0])
    np.testing.assert_allclose(ds.thickness, 1.0)


def test_mismip_plus_tasks():
    component = Landice()
    add_landice_tasks(component)

    paths = [f'mismip_plus/1km/{name}' for name in ['spin_up'] + EXPERIMENTS]
    tasks = [
        path for path in component.tasks if path.startswith('mismip_plus')
    ]
    assert sorted(tasks) == sorted(paths)

    spin_up_task = component.tasks['mismip_plus/1km/spin_up']
    spin_up = spin_up_task.steps['spin_up']
    # other tasks read the steady state from the cache
    assert spin_up.default_cached
    assert spin_up.subdir in spin_up_task.free_running_steps
    assert spin_up.outputs == ['steady_state.nc', 'spin_up_diagnostics.nc']
    spin_up_run = spin_up_task.steps['run']
    viz = spin_up_task.steps['viz']
    inputs = {entry['filename']: entry for entry in viz.input_data}
    assert inputs['global_stats.nc']['work_dir_target'] == (
        f'{spin_up_run.path}/globalStats.nc'
    )

    mesh = spin_up_task.steps['mesh']
    assert mesh.component.name == 'mesh'
    assert mesh.subdir == 'planar/mismip_plus/1km/mesh'

    # every experiment starts from the steady state, or the end of another
    for name in EXPERIMENTS:
        task = component.tasks[f'mismip_plus/1km/{name}']
        assert task.steps['spin_up'] is spin_up
        forward = task.steps[f'{name}_forward']
        inputs = {entry['filename']: entry for entry in forward.input_data}
        assert inputs['steady_state.nc']['work_dir_target'] == (
            f'{spin_up.path}/steady_state.nc'
        )
        # every experiment calves thin floating ice and icebergs
        options = {}
        for data in forward.model_config_data:
            options.update(data.get('options', {}))
        assert options['config_calving'] == 'thickness_threshold'
        assert options['config_calving_thickness'] == 10.0
        assert options['config_remove_icebergs']

    ice1r = component.tasks['mismip_plus/1km/ice1r'].steps['ice1r_forward']
    ice1ra = component.tasks['mismip_plus/1km/ice1ra'].steps['ice1ra_forward']
    assert component.tasks['mismip_plus/1km/ice1ra'].steps[
        'ice1r_forward'
    ] is (ice1r)
    assert (ice1ra.start_year, ice1ra.end_year) == (100, 200)
    inputs = {entry['filename']: entry for entry in ice1ra.input_data}
    assert inputs['restart.00100.nc']['work_dir_target'] == (
        f'{ice1r.path}/restart.00100.nc'
    )
    assert 'restart.00100.nc' in ice1r.outputs

    analysis = component.tasks['mismip_plus/1km/ice1ra'].steps['analysis']
    inputs = {entry['filename']: entry for entry in analysis.input_data}
    assert inputs['previous_global_stats.nc']['work_dir_target'] == (
        f'{ice1r.path}/globalStats.nc'
    )
    assert 'ice1ra_global_stats_flux.png' in analysis.outputs


def test_steady_state_steps_are_shared():
    from polaris.tasks.landice import landice

    component = Landice()
    add_landice_tasks(component)

    # another caller gets the steps and config the tasks use
    steps, config = get_mismip_plus_steady_state_steps(
        resolution=1.0, component=component
    )
    task = component.tasks['mismip_plus/1km/ice0']
    for name in ['mesh', 'init', 'spin_up_run', 'spin_up']:
        assert any(step is steps[name] for step in task.steps.values())
    assert config is steps['spin_up'].config
    assert steps['init'].subdir == 'mismip_plus/1km/init'
    assert steps['spin_up_run'].subdir == 'mismip_plus/1km/spin_up/run'
    assert steps['spin_up'].subdir == 'mismip_plus/1km/spin_up/spin_up'

    # the steps belong to the component they were asked for, not landice
    assert steps['spin_up'].component is component
    assert steps['spin_up'] is not landice.steps.get(steps['spin_up'].subdir)


def test_centerline_position_from_contour():
    # a grounding line that is farthest upstream on the centerline
    y_gl = np.linspace(0.0, 80.0e3, 81)
    x_gl = 400.0e3 + 1e-5 * (y_gl - 40.0e3) ** 2
    position = _centerline_position(x_gl[:, np.newaxis], y_gl[:, np.newaxis])
    np.testing.assert_allclose(position, [400.0e3])

    # no point near the centerline
    position = _centerline_position(
        np.array([[400.0e3]]), np.array([[10.0e3]])
    )
    assert np.isnan(position[0])


def test_gather_entries(tmp_path):
    contents = {
        'ABC_Model_Weertman_1km': _make_entry(
            tmp_path / 'a.nc', n_time=3, transposed=False, vaf_name='iceVAF'
        ),
        'DEF_Model_Tsai_1km': _make_entry(
            tmp_path / 'b.nc', n_time=2, transposed=True, vaf_name='iceVaf'
        ),
    }
    ds = _gather_entries(contents)

    assert list(ds.entry.values) == list(contents.keys())
    assert list(ds.weertman.values) == [True, False]
    np.testing.assert_allclose(ds.time.values[0], [0.0, 10.0, 20.0])
    np.testing.assert_allclose(ds.time.values[1, :2], [0.0, 10.0])
    assert np.isnan(ds.time.values[1, 2])
    np.testing.assert_allclose(ds.iceVAF.values[1, :2], [1.0, 2.0])
    np.testing.assert_allclose(ds.xGL.values[0], [450.0e3, 440.0e3, 430.0e3])


def test_get_restart_year(tmp_path):
    assert get_restart_year(str(tmp_path)) is None
    with open(tmp_path / 'restart_timestamp', 'w') as timestamp_file:
        timestamp_file.write(' 01050-01-01_00:00:00\n')
    assert get_restart_year(str(tmp_path)) == 1050


@pytest.mark.parametrize(
    'end_x_gl, message',
    [
        (450.0e3, None),
        (450.6e3, 'has not converged'),
    ],
)
def test_spin_up_convergence(tmp_path, monkeypatch, end_x_gl, message):
    monkeypatch.chdir(tmp_path)
    os.makedirs('run')
    x_gls = [440.0e3, 445.0e3, 448.0e3, 449.0e3, 450.0e3, end_x_gl]
    _write_spin_up_run(x_gls)
    with open('run/albany_input.yaml', 'w') as albany_file:
        albany_file.write('ANONYMOUS: {}\n')

    step = _get_spin_up_step(run_years=250, convergence_years=50)
    if message is None:
        step.run()
        with netCDF4.Dataset('steady_state.nc') as ds:
            assert ds.mismip_plus_spin_up_years == 250
            np.testing.assert_allclose(
                ds.mismip_plus_grounding_line_x, end_x_gl
            )
        ds_diag = xr.open_dataset('spin_up_diagnostics.nc')
        np.testing.assert_allclose(ds_diag.Time, 50.0 * np.arange(6))
        np.testing.assert_allclose(ds_diag.xGL, x_gls)
    else:
        with pytest.raises(ValueError, match=message):
            step.run()


def test_spin_up_outside_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs('run')
    _write_spin_up_run(6 * [439.0e3])

    step = _get_spin_up_step(run_years=250, convergence_years=250)
    with pytest.raises(ValueError, match='outside 450'):
        step.run()


def test_read_output(tmp_path):
    # a continued run wrote years 50 and 100 again
    xtimes = [
        '0000-01-01_00:00:00',
        '0050-01-01_00:00:00',
        '0100-01-01_00:00:00',
        '0050-01-01_00:00:00',
        '0100-01-01_00:00:00',
        '0150-07-02_12:00:00',
    ]
    ds = xr.Dataset()
    ds['xtime'] = ('Time', np.array(xtimes, dtype='S64'))
    ds['thickness'] = ('Time', np.arange(len(xtimes), dtype=float))
    write_netcdf(ds, str(tmp_path / 'output.nc'))

    ds = read_output(str(tmp_path / 'output.nc'))
    np.testing.assert_allclose(ds.Time, [0.0, 50.0, 100.0, 150.5])
    np.testing.assert_allclose(ds.thickness, [0.0, 3.0, 4.0, 5.0])


def test_plot_global_stats(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    series = []
    for label, start in [('ice1r', 0.0), ('ice1ra', 100.0)]:
        ds = xr.Dataset()
        ds['Time'] = ('Time', start + np.linspace(0.0, 100.0, 11))
        for var, _, _ in GLOBAL_STATS_VOLUME + GLOBAL_STATS_FLUX:
            ds[var] = ('Time', np.linspace(1.0e12, 2.0e12, 11))
        series.append((label, ds))

    plot_global_stats(series, prefix='ice1ra_', title='MISMIP+ Ice1ra')
    for suffix in ['volume', 'flux']:
        assert os.path.exists(f'ice1ra_global_stats_{suffix}.png')


def _make_centerline_dataset(x_gl, x0=436.0e3):
    """
    A row of cells on the centerline from x0, 1 km apart, of area 2 m^2, on
    a bed 1000 m deep, with the grounding line at x_gl
    """
    n_cells = 20
    x = x0 + 1.0e3 * np.arange(n_cells)
    flotation = OCEAN_DENSITY / ICE_DENSITY * 1000.0
    ds = xr.Dataset()
    ds['xCell'] = ('nCells', x)
    ds['yCell'] = ('nCells', 40.0e3 * np.ones(n_cells))
    ds['areaCell'] = ('nCells', 2.0 * np.ones(n_cells))
    ds['dcEdge'] = ('nEdges', [1.0e3])
    # the thickness above flotation falls by 25 m per km
    ds['thickness'] = ('nCells', flotation + 25.0e-3 * (x_gl - x))
    ds['bedTopography'] = ('nCells', -1000.0 * np.ones(n_cells))
    return ds


def _make_entry(filename, n_time, transposed, vaf_name):
    """
    Write a submission like those in the supplement to Cornford et al. (2020)
    and return its contents
    """
    with netCDF4.Dataset(filename, 'w') as ds:
        ds.createDimension('nPointGL', 3)
        ds.createDimension('nTime', n_time)
        time = 10.0 * np.arange(n_time)
        ds.createVariable('time', 'f4', ('nTime',))[:] = time
        for var in ['iceVolume', vaf_name, 'groundedArea']:
            ds.createVariable(var, 'f4', ('nTime',))[:] = 1.0 + np.arange(
                n_time
            )
        x_gl = (
            450.0e3
            - 10.0e3 * np.arange(n_time)[np.newaxis, :]
            + np.array([[0.0], [0.0], [5.0e3]])
        )
        y_gl = np.array([[39.5e3], [40.5e3], [70.0e3]]) * np.ones((1, n_time))
        dims = ('nPointGL', 'nTime')
        if transposed:
            x_gl = x_gl.T
            y_gl = y_gl.T
            dims = ('nTime', 'nPointGL')
        ds.createVariable('xGL', 'f4', dims)[:] = x_gl
        ds.createVariable('yGL', 'f4', dims)[:] = y_gl
    with open(filename, 'rb') as entry_file:
        return entry_file.read()


def _write_spin_up_run(x_gls):
    """
    Write the starting state, MALI's output every 50 years with the grounding
    line at each of x_gls, and the restart at the end, in run/
    """
    ds = _make_centerline_dataset(x_gl=x_gls[0])
    for var in ['thickness', 'bedTopography']:
        ds[var] = ds[var].expand_dims('Time')
    write_netcdf(ds, 'run/landice_grid.nc')

    snapshots = []
    for x_gl in x_gls:
        ds = _make_centerline_dataset(x_gl=x_gl)
        snapshots.append(ds[['thickness', 'bedTopography']])
    ds = xr.concat(snapshots, dim='Time')
    years = 50 * np.arange(len(x_gls))
    xtimes = [f'{year:04d}-01-01_00:00:00' for year in years]
    ds['xtime'] = ('Time', np.array(xtimes, dtype='S64'))
    write_netcdf(ds, 'run/output.nc')

    ds = _make_centerline_dataset(x_gl=x_gls[-1])
    for var in ['thickness', 'bedTopography']:
        ds[var] = ds[var].expand_dims('Time')
    write_netcdf(ds, f'run/restart.{years[-1]:05d}.nc')


def _get_spin_up_step(run_years, convergence_years):
    """
    The spin-up step, with config options for a short spin-up
    """
    component = Landice()
    add_landice_tasks(component)
    step = component.tasks['mismip_plus/1km/spin_up'].steps['spin_up']
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.landice.mismip_plus', 'mismip_plus.cfg'
    )
    config.set('mismip_plus_spin_up', 'run_years', f'{run_years}')
    config.set(
        'mismip_plus_spin_up', 'convergence_years', f'{convergence_years}'
    )
    step.config = config
    step.logger = logging.getLogger(__name__)
    return step
