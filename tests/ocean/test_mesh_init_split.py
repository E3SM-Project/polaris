import importlib
from configparser import ConfigParser
from unittest.mock import MagicMock

import gsw
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.model_step import ModelStep
from polaris.ocean.model import OceanIOStep, OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.yaml import PolarisYaml


def _make_config(
    horiz_mesh_filename='mesh.nc',
    vert_coord_filename='vert_coord.nc',
    init_filename='init.nc',
    forcing_filename='forcing.nc',
    model='omega',
):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.add_section('ocean_staged_files')
    config.set(
        'ocean_staged_files', 'horiz_mesh_filename', horiz_mesh_filename
    )
    config.set(
        'ocean_staged_files', 'vert_coord_filename', vert_coord_filename
    )
    config.set('ocean_staged_files', 'init_filename', init_filename)
    config.set('ocean_staged_files', 'forcing_filename', forcing_filename)
    return config


def _make_surface_pressure_config(model, surface_pressure=101325.0):
    """Return a config with the options write_initial_state_dataset reads."""
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'surface_pressure', str(surface_pressure))
    return config


def _make_state_ds(surface_pressure=None):
    """Return a minimal initial-state dataset, optionally with a surface
    pressure already set."""
    data_vars: dict = dict(
        normalVelocity=(('nEdges', 'nVertLevels'), [[0.0], [0.0]]),
        # layerThickness is a state variable for MPAS-Ocean and
        # PseudoThickness for Omega
        layerThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
        PseudoThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
        temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
        salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
    )
    if surface_pressure is not None:
        data_vars['SurfacePressure'] = ('nCells', surface_pressure)
    return xr.Dataset(data_vars=data_vars)


def _make_ref_coord_ds():
    """A minimal initial state plus the four 1D reference coordinate vars."""
    ds = _make_state_ds()
    ds['refTopDepth'] = ('nVertLevels', [0.0])
    ds['refZMid'] = ('nVertLevels', [-5.0])
    ds['refBottomDepth'] = ('nVertLevels', [10.0])
    ds['refInterfaces'] = ('nVertLevelsP1', [0.0, 10.0])
    return ds


def test_write_initial_state_dataset_omega_drops_horiz_mesh_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0]),
            fCell=('nCells', [1.0, 2.0]),
            normalVelocity=(('nEdges', 'nVertLevels'), [[0.0], [0.0]]),
            layerThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
            SurfacePressure=('nCells', [0.0, 0.0]),
            PseudoThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'temperature' not in ds_out
    assert 'XCell' not in ds_out
    assert 'FCell' not in ds_out


def test_write_initial_state_dataset_omega_drops_vert_coord_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            normalVelocity=(('nEdges', 'nVertLevels'), [[0.0], [0.0]]),
            RefPseudoThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
            PseudoThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
            SurfacePressure=('nCells', [0.0, 0.0]),
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'SurfacePressure' in ds_out
    assert 'MinLayerCell' not in ds_out
    assert 'MaxLayerCell' not in ds_out
    assert 'BottomGeomDepth' not in ds_out
    assert 'VertCoordMovementWeights' not in ds_out
    assert 'RefPseudoThickness' not in ds_out


def test_write_initial_state_dataset_omega_does_not_rebuild_ref_thickness(
    tmp_path,
):
    """restingThickness does not put RefPseudoThickness back into init.nc.

    RefPseudoThickness belongs to the vertical coordinate file.  It used to
    be dropped by remove_vert_coord_vars() and then immediately recreated
    from restingThickness on the way out, at whatever surface pressure the
    dataset happened to carry -- and labelled as a plain pseudo-thickness,
    disagreeing with the same variable in vert_coord.nc.
    """
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    ds = _make_tracer_state_ds()
    ds['layerThickness'] = (('nCells', 'nVertLevels'), [[10.0], [10.0]])
    ds['restingThickness'] = (('nCells', 'nVertLevels'), [[10.0], [10.0]])
    ds['SurfacePressure'] = ('nCells', [0.0, 0.0])

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        ds, str(filename), _make_tracer_config('omega')
    )

    ds_out = xr.open_dataset(filename)
    assert 'RefPseudoThickness' not in ds_out
    # the layerThickness -> PseudoThickness conversion still runs; only the
    # resting-thickness one is gone
    assert 'PseudoThickness' in ds_out


def test_write_initial_state_dataset_mpas_ocean_keeps_vert_coord_vars(
    tmp_path,
):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            normalVelocity=(('nEdges', 'nVertLevels'), [[0.0], [0.0]]),
            layerThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'temperature' in ds_out
    assert 'minLevelCell' in ds_out
    assert 'maxLevelCell' in ds_out
    assert 'bottomDepth' in ds_out
    assert 'vertCoordMovementWeights' in ds_out


def test_write_initial_state_dataset_omega_adds_surface_pressure(tmp_path):
    """Omega requires a surface pressure, so it is added from the config
    option when a task has not provided one."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_state_ds(),
        str(filename),
        _make_surface_pressure_config('omega'),
    )

    ds_out = xr.open_dataset(filename)
    # SurfacePressure is an Omega-only field; the lowercase MPAS-Ocean name
    # must never appear
    assert 'surfacePressure' not in ds_out
    assert_allclose(ds_out.SurfacePressure.values, [101325.0, 101325.0])
    assert ds_out.SurfacePressure.dims == ('NCells',)
    assert ds_out.SurfacePressure.attrs['units'] == 'Pa'


def test_write_initial_state_dataset_omega_keeps_task_surface_pressure(
    tmp_path,
):
    """A surface pressure set by a task is preserved, not overwritten by the
    config default."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_state_ds(surface_pressure=[1234.0, 5678.0]),
        str(filename),
        _make_surface_pressure_config('omega'),
    )

    ds_out = xr.open_dataset(filename)
    assert 'surfacePressure' not in ds_out
    assert_allclose(ds_out.SurfacePressure.values, [1234.0, 5678.0])


def test_write_initial_state_dataset_mpas_ocean_omits_surface_pressure(
    tmp_path,
):
    """Surface pressure is required by Omega only, so it must not appear in
    MPAS-Ocean initial conditions under either name."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_state_ds(),
        str(filename),
        _make_surface_pressure_config('mpas-ocean'),
    )

    ds_out = xr.open_dataset(filename)
    assert 'surfacePressure' not in ds_out
    assert 'SurfacePressure' not in ds_out


def test_write_initial_state_dataset_omega_drops_ref_coord_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = _make_surface_pressure_config('omega')

    ds = _make_ref_coord_ds()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    for var in ('refTopDepth', 'refZMid', 'refBottomDepth', 'refInterfaces'):
        assert var not in ds_out


def test_write_initial_state_dataset_mpas_ocean_keeps_ref_coord_vars(
    tmp_path,
):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = _make_surface_pressure_config('mpas-ocean')

    ds = _make_ref_coord_ds()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'temperature' in ds_out
    for var in ('refTopDepth', 'refZMid', 'refBottomDepth', 'refInterfaces'):
        assert var in ds_out


def _make_tracer_config(
    model, eos_type='teos-10', nominal_lon=0.0, nominal_lat=0.0
):
    """Return a config with the options the tracer conversion reads."""
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.set('ocean', 'eos_type', eos_type)
    config.set('ocean', 'nominal_lon', str(nominal_lon))
    config.set('ocean', 'nominal_lat', str(nominal_lat))
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'surface_pressure', '0.0')
    config.set('vertical_grid', 'pseudothickness_iter_count', '4')
    return config


# tracers and pressure used by the conversion tests below
CT = np.array([[3.0], [4.0]])
SA = np.array([[35.0], [34.5]])
PRESSURE = np.array([[1.0e6], [2.0e6]])


def _make_tracer_state_ds(on_a_sphere=None, lon_cell=None, lat_cell=None):
    """Return an initial-state dataset with tracers to convert, optionally on
    a spherical mesh with per-cell locations."""
    data_vars: dict = dict(
        normalVelocity=(('nEdges', 'nVertLevels'), [[0.0], [0.0]]),
        layerThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
        PseudoThickness=(('nCells', 'nVertLevels'), [[1.0], [1.0]]),
        temperature=(('nCells', 'nVertLevels'), CT),
        salinity=(('nCells', 'nVertLevels'), SA),
        pressure=(('nCells', 'nVertLevels'), PRESSURE),
    )
    if lon_cell is not None:
        data_vars['lonCell'] = ('nCells', np.deg2rad(lon_cell))
        data_vars['latCell'] = ('nCells', np.deg2rad(lat_cell))
    attrs = {} if on_a_sphere is None else dict(on_a_sphere=on_a_sphere)
    return xr.Dataset(data_vars=data_vars, attrs=attrs)


def _expected_mpas_ocean_tracers(lon, lat):
    """The MPAS-Ocean-convention tracers expected at the given location(s)."""
    pot_temp = gsw.pt_from_CT(SA, CT)
    prac_sal = gsw.SP_from_SA(
        SA,
        PRESSURE / 1.0e4,
        np.reshape(lon, (-1, 1)),
        np.reshape(lat, (-1, 1)),
    )
    return pot_temp, prac_sal


def test_write_initial_state_dataset_converts_tracers_for_mpas_ocean(tmp_path):
    """With TEOS-10, tracers built as CT/SA are converted to PT/SP for
    MPAS-Ocean, without touching the caller's dataset."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    ds = _make_tracer_state_ds()
    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        ds, str(filename), _make_tracer_config('mpas-ocean')
    )

    pot_temp, prac_sal = _expected_mpas_ocean_tracers(0.0, 0.0)
    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.temperature.values, pot_temp)
    assert_allclose(ds_out.salinity.values, prac_sal)
    assert ds_out.temperature.attrs['long_name'] == 'potential temperature'
    assert ds_out.salinity.attrs['units'] == 'PSU'
    # the in-memory dataset the step handed over is untouched
    assert_allclose(ds.temperature.values, CT)
    assert_allclose(ds.salinity.values, SA)


def test_write_initial_state_dataset_keeps_teos10_tracers_for_omega(tmp_path):
    """Omega uses the TEOS-10 convention, so tracers pass through."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_tracer_state_ds(), str(filename), _make_tracer_config('omega')
    )

    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.Temperature.values, CT)
    assert_allclose(ds_out.Salinity.values, SA)


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_write_initial_state_dataset_no_conversion_for_linear_eos(
    tmp_path, model
):
    """The two conventions are indistinguishable for a linear EOS, so no
    conversion happens even if one is requested explicitly."""
    component = Ocean()
    component.model = model
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_tracer_state_ds(),
        str(filename),
        _make_tracer_config(model, eos_type='linear'),
        tracer_convention='teos-10',
    )

    ds_out = xr.open_dataset(filename)
    temperature = component.map_var_list_to_native_model(['temperature'])[0]
    assert_allclose(ds_out[temperature].values, CT)


def test_write_initial_state_dataset_converts_tracers_for_omega(tmp_path):
    """A task that builds PT/SP under TEOS-10 gets the reverse conversion when
    running Omega."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_tracer_state_ds(),
        str(filename),
        _make_tracer_config('omega'),
        tracer_convention='mpas-ocean',
    )

    abs_sal = gsw.SA_from_SP(SA, PRESSURE / 1.0e4, 0.0, 0.0)
    cons_temp = gsw.CT_from_pt(abs_sal, CT)
    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.Temperature.values, cons_temp)
    assert_allclose(ds_out.Salinity.values, abs_sal)
    assert ds_out.Temperature.attrs['long_name'] == 'conservative temperature'


def test_write_initial_state_dataset_converts_at_cell_locations(tmp_path):
    """On a spherical mesh, each cell is converted at its own location rather
    than at the nominal one."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    lon_cell = np.array([0.0, 180.0])
    lat_cell = np.array([-60.0, 30.0])
    ds = _make_tracer_state_ds(
        on_a_sphere='YES', lon_cell=lon_cell, lat_cell=lat_cell
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        ds,
        str(filename),
        # the nominal location must be ignored
        _make_tracer_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
    )

    _, prac_sal = _expected_mpas_ocean_tracers(lon_cell, lat_cell)
    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.salinity.values, prac_sal)


def test_write_initial_state_dataset_converts_at_nominal_location(tmp_path):
    """On a planar mesh, lonCell/latCell are meaningless, so the nominal
    location is used instead."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    ds = _make_tracer_state_ds(
        on_a_sphere='NO',
        lon_cell=np.array([0.0, 180.0]),
        lat_cell=np.array([-60.0, 30.0]),
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        ds,
        str(filename),
        _make_tracer_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
    )

    _, prac_sal = _expected_mpas_ocean_tracers(90.0, -45.0)
    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.salinity.values, prac_sal)


def test_write_initial_state_dataset_uses_explicit_lon_lat(tmp_path):
    """Explicit lon/lat arguments win over the mesh and the config."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_tracer_state_ds(),
        str(filename),
        _make_tracer_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
        lon=-30.0,
        lat=15.0,
    )

    _, prac_sal = _expected_mpas_ocean_tracers(-30.0, 15.0)
    ds_out = xr.open_dataset(filename)
    assert_allclose(ds_out.salinity.values, prac_sal)


def test_write_initial_state_dataset_raises_without_cell_locations(tmp_path):
    """A spherical mesh without lonCell/latCell means something upstream
    dropped them, so falling back to the nominal location would be wrong."""
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    with pytest.raises(ValueError, match='lonCell'):
        component.write_initial_state_dataset(
            _make_tracer_state_ds(on_a_sphere='YES'),
            str(filename),
            _make_tracer_config('mpas-ocean'),
        )


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_write_initial_state_dataset_drops_pressure(tmp_path, model):
    """pressure is only an intermediate for the tracer conversion, so it does
    not belong in the initial state."""
    component = Ocean()
    component.model = model
    component._read_var_map()

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(
        _make_tracer_state_ds(),
        str(filename),
        _make_tracer_config(model),
    )

    ds_out = xr.open_dataset(filename)
    assert 'pressure' not in ds_out
    assert 'Pressure' not in ds_out


def test_write_vert_coord_dataset_noop_for_mpas_ocean(tmp_path):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            restingThickness=(
                ('nCells', 'nVertLevels'),
                [[50.0], [100.0]],
            ),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'vert_coord.nc'
    component.write_vert_coord_dataset(ds, str(filename), config)

    assert not filename.exists()


@pytest.mark.parametrize(
    'model,missing_var',
    [
        ('mpas-ocean', 'restingThickness'),
        ('omega', 'RefPseudoThickness'),
    ],
)
def test_write_vert_coord_dataset_raises_on_missing_vars(
    tmp_path, model, missing_var
):
    component = Ocean()
    component.model = model
    component._read_var_map()

    config = MagicMock()

    # omit the model-specific thickness var and vertCoordMovementWeights
    ds = xr.Dataset(
        data_vars=dict(
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
            bottomDepth=('nCells', [100.0, 200.0]),
        )
    )

    filename = tmp_path / 'vert_coord.nc'
    with pytest.raises(ValueError, match=missing_var):
        component.write_vert_coord_dataset(ds, str(filename), config)


def _make_horiz_mesh_ds(component):
    """Build a minimal dataset with all horiz_mesh_vars as dummy data."""
    return xr.Dataset(
        data_vars={
            v: ('nCells', [0.0, 1.0]) for v in component.horiz_mesh_vars
        }
    )


def test_write_horiz_mesh_dataset_raises_on_missing_vars(tmp_path):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()

    # dataset is missing most horiz_mesh_vars
    ds = xr.Dataset(data_vars=dict(xCell=('nCells', [0.0, 1.0])))

    filename = tmp_path / 'mesh.nc'
    with pytest.raises(ValueError, match='indexToCellID'):
        component.write_horiz_mesh_dataset(ds, str(filename), config)


def test_write_horiz_mesh_dataset_writes_mpas_ocean(tmp_path):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()
    ds = _make_horiz_mesh_ds(component)

    filename = tmp_path / 'mesh.nc'
    component.write_horiz_mesh_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'xCell' in ds_out
    assert 'fCell' in ds_out


def test_write_horiz_mesh_dataset_writes_omega(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = MagicMock()
    ds = _make_horiz_mesh_ds(component)

    filename = tmp_path / 'mesh.nc'
    component.write_horiz_mesh_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'XCell' in ds_out
    assert 'FCell' in ds_out
    assert 'xCell' not in ds_out


def test_process_inputs_and_outputs_resolves_model_input_filenames(
    monkeypatch,
):
    component = Ocean()
    component.model = 'omega'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(
        horiz_mesh_filename='custom_mesh.nc',
        vert_coord_filename='custom_vc.nc',
        init_filename='custom_init.nc',
        forcing_filename='custom_forcing.nc',
    )

    step.add_horiz_mesh_input_file(work_dir_target='mesh_target.nc')
    step.add_vert_coord_input_file(work_dir_target='vc_target.nc')
    step.add_init_input_file(work_dir_target='init_target.nc')
    step.add_forcing_input_file(work_dir_target='forcing_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    input_data = {
        entry['work_dir_target']: entry['filename']
        for entry in step.input_data
        if entry.get('work_dir_target') is not None
    }
    assert input_data['mesh_target.nc'] == 'custom_mesh.nc'
    assert input_data['vc_target.nc'] == 'custom_vc.nc'
    assert input_data['init_target.nc'] == 'custom_init.nc'
    assert input_data['forcing_target.nc'] == 'custom_forcing.nc'


def test_forcing_placeholder_is_kept_for_mpas_ocean(monkeypatch):
    """
    Unlike the vertical coordinate, both models read a forcing file, so the
    placeholder must survive for MPAS-Ocean too.
    """
    component = Ocean()
    component.model = 'mpas-ocean'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(model='mpas-ocean')
    step.add_forcing_input_file(work_dir_target='forcing_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    filenames = [entry['filename'] for entry in step.input_data]
    assert 'forcing.nc' in filenames
    assert '<<<forcing>>>' not in filenames


def test_vert_coord_placeholder_skipped_for_mpas_ocean(monkeypatch):
    component = Ocean()
    component.model = 'mpas-ocean'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(model='mpas-ocean')
    step.add_vert_coord_input_file(work_dir_target='vc_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    filenames = [entry['filename'] for entry in step.input_data]
    assert 'vert_coord.nc' not in filenames
    assert '<<<vert_coord>>>' not in filenames


def test_dynamic_model_config_uses_model_input_filename_replacements():
    component = Ocean()
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(
        horiz_mesh_filename='custom_mesh.nc',
        vert_coord_filename='custom_vc.nc',
        init_filename='custom_init.nc',
    )

    step.dynamic_model_config(at_setup=True)

    entry = step.model_config_data[0]
    yaml = PolarisYaml.read(
        filename=entry['yaml'],
        package=entry['package'],
        replacements=entry['replacements'],
        model='Omega',
        streams_section='IOStreams',
    )
    assert yaml.streams['HorzMeshIn']['Filename'] == 'custom_mesh.nc'
    assert yaml.streams['InitialVertCoord']['Filename'] == 'custom_vc.nc'
    assert yaml.streams['InitialState']['Filename'] == 'custom_init.nc'


@pytest.mark.parametrize(
    'module_name',
    [
        'polaris.tasks.ocean.baroclinic_channel.init',
        'polaris.tasks.ocean.barotropic_channel.init',
        'polaris.tasks.ocean.geostrophic.init',
        'polaris.tasks.ocean.ice_shelf_2d.init',
        'polaris.tasks.ocean.inertial_gravity_wave.init',
        'polaris.tasks.ocean.internal_wave.init',
        'polaris.tasks.ocean.single_column.init',
    ],
)
def test_init_steps_with_ocean_model_io_descend_from_ocean_io_step(
    module_name,
):
    module = importlib.import_module(module_name)
    assert issubclass(module.Init, OceanIOStep)
