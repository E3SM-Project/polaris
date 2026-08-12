import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean import Ocean


def _stress_dataset(n_cells=5):
    ds = xr.Dataset(
        {
            'windStressZonal': ('nCells', np.linspace(-0.1, 0.2, n_cells)),
            'windStressMeridional': (
                'nCells',
                np.linspace(0.05, -0.05, n_cells),
            ),
        }
    )
    for name in ['windStressZonal', 'windStressMeridional']:
        ds[name].attrs = {'units': 'N m-2'}
    return ds


def _write(model, ds, tmp_path):
    component = Ocean()
    component.model = model
    filename = str(tmp_path / 'forcing.nc')
    component.write_forcing_dataset(ds, filename, config=None)
    return xr.open_dataset(filename)


def test_omega_forcing_has_no_time_dimension(tmp_path):
    """
    Omega's SfcStressForcingVars registers 1-D fields on NCells, and its
    Forcing stream is read once at start-up.
    """
    ds_out = _write('omega', _stress_dataset(), tmp_path)
    assert set(ds_out.data_vars) == {'SfcStressZonal', 'SfcStressMeridional'}
    assert 'Time' not in ds_out.sizes
    for name in ds_out.data_vars:
        assert ds_out[name].dims == ('NCells',)


def test_mpas_ocean_forcing_has_a_time_dimension(tmp_path):
    """
    MPAS-Ocean's Registry declares dimensions="nCells Time" for
    windStressZonal/windStressMeridional, so a Time dimension of one is
    required.
    """
    ds_out = _write('mpas-ocean', _stress_dataset(), tmp_path)
    assert set(ds_out.data_vars) == {
        'windStressZonal',
        'windStressMeridional',
    }
    assert ds_out.sizes['Time'] == 1
    for name in ds_out.data_vars:
        assert ds_out[name].dims == ('Time', 'nCells')


@pytest.mark.parametrize('model', ['omega', 'mpas-ocean'])
def test_forcing_values_and_units_survive(model, tmp_path):
    ds = _stress_dataset()
    ds_out = _write(model, ds, tmp_path)
    zonal = ds_out['SfcStressZonal' if model == 'omega' else 'windStressZonal']
    np.testing.assert_allclose(
        np.asarray(zonal.values).ravel(), ds.windStressZonal.values
    )
    assert zonal.attrs['units'] == 'N m-2'


@pytest.mark.parametrize('model', ['omega', 'mpas-ocean'])
def test_missing_forcing_variable_raises(model, tmp_path):
    ds = _stress_dataset().drop_vars('windStressMeridional')
    with pytest.raises(ValueError, match='write_forcing_dataset'):
        _write(model, ds, tmp_path)
