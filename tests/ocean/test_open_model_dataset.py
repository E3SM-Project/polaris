from configparser import ConfigParser

import gsw
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.tasks.ocean import Ocean

# tracers and pressure used by the conversion tests below
CT = np.array([[3.0], [4.0]])
SA = np.array([[35.0], [34.5]])
PT = np.array([[3.1], [4.1]])
SP = np.array([[34.9], [34.4]])
PRESSURE = np.array([[1.0e6], [2.0e6]])


def _make_component(model):
    component = Ocean()
    component.model = model
    component._read_var_map()
    return component


def _make_config(model, eos_type='teos-10', nominal_lon=0.0, nominal_lat=0.0):
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


def _write_output_file(
    path, model, temperature=CT, salinity=SA, pressure=PRESSURE
):
    """Write a file of model output with the tracers and a pressure, in the
    variable names the given model uses."""
    if model == 'omega':
        names = ('Temperature', 'Salinity', 'PressureMid')
        dims = ('NCells', 'NVertLayers')
    else:
        names = ('temperature', 'salinity', 'pressure')
        dims = ('nCells', 'nVertLevels')
    data_vars = {
        names[0]: (dims, temperature),
        names[1]: (dims, salinity),
    }
    if pressure is not None:
        data_vars[names[2]] = (dims, pressure)
    xr.Dataset(data_vars=data_vars).to_netcdf(path)
    return str(path)


def _write_mesh_file(path, on_a_sphere=None, lon_cell=None, lat_cell=None):
    """Write a mesh file, optionally spherical with per-cell locations."""
    data_vars: dict = dict(xCell=('nCells', [0.0, 1.0]))
    if lon_cell is not None:
        data_vars['lonCell'] = ('nCells', np.deg2rad(lon_cell))
        data_vars['latCell'] = ('nCells', np.deg2rad(lat_cell))
    attrs = {} if on_a_sphere is None else dict(on_a_sphere=on_a_sphere)
    xr.Dataset(data_vars=data_vars, attrs=attrs).to_netcdf(path)
    return str(path)


def _expected_teos10_tracers(lon, lat):
    """The TEOS-10-convention tracers expected from PT/SP at the given
    location(s)."""
    abs_sal = gsw.SA_from_SP(
        SP,
        PRESSURE / 1.0e4,
        np.reshape(lon, (-1, 1)),
        np.reshape(lat, (-1, 1)),
    )
    return gsw.CT_from_pt(abs_sal, PT), abs_sal


def test_open_model_dataset_converts_mpas_ocean_tracers(tmp_path):
    """MPAS-Ocean output can be read as conservative temperature and absolute
    salinity."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(
        tmp_path / 'output.nc', 'mpas-ocean', temperature=PT, salinity=SP
    )
    mesh_filename = _write_mesh_file(tmp_path / 'mesh.nc', on_a_sphere='NO')

    ds = component.open_model_dataset(
        filename,
        _make_config('mpas-ocean'),
        mesh_filename=mesh_filename,
        tracer_convention='teos-10',
    )

    cons_temp, abs_sal = _expected_teos10_tracers(0.0, 0.0)
    assert_allclose(ds.temperature.values, cons_temp)
    assert_allclose(ds.salinity.values, abs_sal)
    assert ds.temperature.attrs['long_name'] == 'conservative temperature'
    assert ds.salinity.attrs['units'] == 'g kg-1'


def test_open_model_dataset_keeps_omega_teos10_tracers(tmp_path):
    """Omega already writes the TEOS-10 convention, so its tracers pass
    through."""
    component = _make_component('omega')
    filename = _write_output_file(tmp_path / 'output.nc', 'omega')

    ds = component.open_model_dataset(
        filename,
        _make_config('omega'),
        tracer_convention='teos-10',
    )

    assert_allclose(ds.temperature.values, CT)
    assert_allclose(ds.salinity.values, SA)


def test_open_model_dataset_converts_omega_tracers(tmp_path):
    """Omega output can be read in the MPAS-Ocean convention, the reverse of
    the conversion done for MPAS-Ocean output."""
    component = _make_component('omega')
    filename = _write_output_file(tmp_path / 'output.nc', 'omega')

    ds = component.open_model_dataset(
        filename,
        _make_config('omega'),
        tracer_convention='mpas-ocean',
        lon=-30.0,
        lat=15.0,
    )

    pot_temp = gsw.pt_from_CT(SA, CT)
    prac_sal = gsw.SP_from_SA(SA, PRESSURE / 1.0e4, -30.0, 15.0)
    assert_allclose(ds.temperature.values, pot_temp)
    assert_allclose(ds.salinity.values, prac_sal)
    assert ds.temperature.attrs['long_name'] == 'potential temperature'


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_open_model_dataset_leaves_tracers_alone_by_default(tmp_path, model):
    """A caller that does not ask for a convention gets the tracers exactly as
    the model wrote them."""
    component = _make_component(model)
    filename = _write_output_file(tmp_path / 'output.nc', model)

    ds = component.open_model_dataset(filename, _make_config(model))

    assert_allclose(ds.temperature.values, CT)
    assert_allclose(ds.salinity.values, SA)


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_open_model_dataset_no_conversion_for_linear_eos(tmp_path, model):
    """The two conventions are indistinguishable for a linear EOS, so no
    conversion happens even if one is requested explicitly."""
    component = _make_component(model)
    filename = _write_output_file(tmp_path / 'output.nc', model)

    ds = component.open_model_dataset(
        filename,
        _make_config(model, eos_type='linear'),
        tracer_convention='mpas-ocean',
    )

    assert_allclose(ds.temperature.values, CT)
    assert_allclose(ds.salinity.values, SA)


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_initial_state_tracers_survive_a_round_trip(tmp_path, model):
    """Tracers written in one convention and read back in the other are the
    ones the step built."""
    component = _make_component(model)
    config = _make_config(model)
    cell_dims = ('Time', 'nCells', 'nVertLevels')
    ds = xr.Dataset(
        data_vars=dict(
            temperature=(cell_dims, CT[np.newaxis, :, :]),
            salinity=(cell_dims, SA[np.newaxis, :, :]),
            layerThickness=(cell_dims, np.array([[[100.0], [200.0]]])),
            normalVelocity=(
                ('Time', 'nEdges', 'nVertLevels'),
                np.zeros((1, 2, 1)),
            ),
            SurfacePressure=(('Time', 'nCells'), np.zeros((1, 2))),
            minLevelCell=('nCells', [1, 1]),
            maxLevelCell=('nCells', [1, 1]),
            bottomDepth=('nCells', [100.0, 200.0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = str(tmp_path / 'init.nc')
    component.write_initial_state_dataset(ds, filename, config, lon=1.0, lat=2)

    ds_out = component.open_model_dataset(
        filename,
        config,
        tracer_convention='teos-10',
        lon=1.0,
        lat=2.0,
    )

    assert_allclose(ds_out.temperature.values, CT[np.newaxis, :, :], atol=1e-6)
    assert_allclose(ds_out.salinity.values, SA[np.newaxis, :, :], atol=1e-6)


def test_open_model_dataset_converts_at_cell_locations(tmp_path):
    """On a spherical mesh, each cell is converted at its own location rather
    than at the nominal one."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(
        tmp_path / 'output.nc', 'mpas-ocean', temperature=PT, salinity=SP
    )
    lon_cell = np.array([0.0, 180.0])
    lat_cell = np.array([-60.0, 30.0])
    mesh_filename = _write_mesh_file(
        tmp_path / 'mesh.nc',
        on_a_sphere='YES',
        lon_cell=lon_cell,
        lat_cell=lat_cell,
    )

    ds = component.open_model_dataset(
        filename,
        # the nominal location must be ignored
        _make_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
        mesh_filename=mesh_filename,
        tracer_convention='teos-10',
    )

    _, abs_sal = _expected_teos10_tracers(lon_cell, lat_cell)
    assert_allclose(ds.salinity.values, abs_sal)


def test_open_model_dataset_converts_at_nominal_location(tmp_path):
    """On a planar mesh, the nominal location from config is used."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(
        tmp_path / 'output.nc', 'mpas-ocean', temperature=PT, salinity=SP
    )
    mesh_filename = _write_mesh_file(
        tmp_path / 'mesh.nc',
        on_a_sphere='NO',
        lon_cell=np.array([0.0, 180.0]),
        lat_cell=np.array([-60.0, 30.0]),
    )

    ds = component.open_model_dataset(
        filename,
        _make_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
        mesh_filename=mesh_filename,
        tracer_convention='teos-10',
    )

    _, abs_sal = _expected_teos10_tracers(90.0, -45.0)
    assert_allclose(ds.salinity.values, abs_sal)


def test_open_model_dataset_uses_explicit_lon_lat(tmp_path):
    """Explicit lon/lat arguments win over the mesh and the config."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(
        tmp_path / 'output.nc', 'mpas-ocean', temperature=PT, salinity=SP
    )
    mesh_filename = _write_mesh_file(
        tmp_path / 'mesh.nc',
        on_a_sphere='YES',
        lon_cell=np.array([0.0, 180.0]),
        lat_cell=np.array([-60.0, 30.0]),
    )

    ds = component.open_model_dataset(
        filename,
        _make_config('mpas-ocean', nominal_lon=90.0, nominal_lat=-45.0),
        mesh_filename=mesh_filename,
        tracer_convention='teos-10',
        lon=-30.0,
        lat=15.0,
    )

    _, abs_sal = _expected_teos10_tracers(-30.0, 15.0)
    assert_allclose(ds.salinity.values, abs_sal)


def test_open_model_dataset_raises_without_a_location(tmp_path):
    """A dataset being read has no mesh variables of its own, so a conversion
    needs either a mesh file or an explicit location."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(tmp_path / 'output.nc', 'mpas-ocean')

    with pytest.raises(ValueError, match='mesh_filename'):
        component.open_model_dataset(
            filename,
            _make_config('mpas-ocean'),
            tracer_convention='teos-10',
        )


def test_open_model_dataset_raises_without_on_a_sphere(tmp_path):
    """A mesh with no on_a_sphere attribute is invalid, and assuming it is
    planar would silently convert a global ocean at (0, 0)."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(tmp_path / 'output.nc', 'mpas-ocean')
    mesh_filename = _write_mesh_file(tmp_path / 'mesh.nc')

    with pytest.raises(ValueError, match='on_a_sphere'):
        component.open_model_dataset(
            filename,
            _make_config('mpas-ocean'),
            mesh_filename=mesh_filename,
            tracer_convention='teos-10',
        )


def test_open_model_dataset_raises_without_cell_locations(tmp_path):
    """A spherical mesh without lonCell/latCell means something upstream
    dropped them, so falling back to the nominal location would be wrong."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(tmp_path / 'output.nc', 'mpas-ocean')
    mesh_filename = _write_mesh_file(tmp_path / 'mesh.nc', on_a_sphere='YES')

    with pytest.raises(ValueError, match='lonCell'):
        component.open_model_dataset(
            filename,
            _make_config('mpas-ocean'),
            mesh_filename=mesh_filename,
            tracer_convention='teos-10',
        )


def test_open_model_dataset_raises_on_missing_tracers(tmp_path):
    """Asking to convert a file with no tracers, such as a mesh file, is a
    mistake rather than something to skip silently."""
    component = _make_component('mpas-ocean')
    filename = _write_mesh_file(tmp_path / 'mesh.nc', on_a_sphere='NO')

    with pytest.raises(ValueError, match='temperature'):
        component.open_model_dataset(
            filename,
            _make_config('mpas-ocean'),
            mesh_filename=filename,
            tracer_convention='teos-10',
        )


def test_open_model_dataset_uses_the_pressure_in_the_file(tmp_path):
    """Omega writes a mid-layer pressure, which is used rather than
    recomputing one from the layer thicknesses."""
    component = _make_component('omega')
    filename = _write_output_file(tmp_path / 'output.nc', 'omega')

    ds = component.open_model_dataset(
        filename,
        _make_config('omega'),
        tracer_convention='mpas-ocean',
        lon=0.0,
        lat=0.0,
    )

    prac_sal = gsw.SP_from_SA(SA, PRESSURE / 1.0e4, 0.0, 0.0)
    assert_allclose(ds.salinity.values, prac_sal)


def test_open_model_dataset_raises_without_a_pressure(tmp_path):
    """Without a pressure or the fields to compute one, there is no way to
    convert."""
    component = _make_component('mpas-ocean')
    filename = _write_output_file(
        tmp_path / 'output.nc', 'mpas-ocean', pressure=None
    )

    with pytest.raises(ValueError, match='layerThickness'):
        component.open_model_dataset(
            filename,
            _make_config('mpas-ocean'),
            tracer_convention='teos-10',
            lon=0.0,
            lat=0.0,
        )
