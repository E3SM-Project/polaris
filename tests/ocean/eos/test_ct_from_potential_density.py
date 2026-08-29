import gsw
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.eos import ct_from_potential_density


def test_round_trip_scalar():
    sigma_0 = 1026.5
    ct = ct_from_potential_density(sigma_0, 35.0)

    assert isinstance(ct, float)
    assert_allclose(gsw.rho(35.0, ct, 0.0), sigma_0)


def test_round_trip_data_array():
    # a Beckmann and Haidvogel exponential profile over a 5000 m column
    z_mid = -np.linspace(78.125, 4921.875, 32)
    # built explicitly rather than by arithmetic on a DataArray: numpy's
    # signatures say a ufunc returns an ndarray, so the DataArray that
    # xarray really hands back is invisible to a type checker
    sigma_0 = xr.DataArray(
        1028.0 - 3.0 * np.exp(z_mid / 500.0), dims=('nVertLevels',)
    )

    ct = ct_from_potential_density(sigma_0, 35.0)

    assert isinstance(ct, xr.DataArray)
    assert ct.dims == sigma_0.dims
    assert ct.attrs['units'] == 'degC'
    # the inversion is exact, not iterative, so this should close to
    # round-off rather than to a solver tolerance
    assert_allclose(gsw.rho(35.0, ct.values, 0.0), sigma_0.values, atol=1e-11)


def test_salinity_varies_with_density():
    sigma_0 = xr.DataArray(np.array([1025.0, 1027.0]), dims=('nCells',))
    sa = xr.DataArray(np.array([34.0, 35.5]), dims=('nCells',))

    ct = ct_from_potential_density(sigma_0, sa)

    assert isinstance(ct, xr.DataArray)
    assert_allclose(
        gsw.rho(sa.values, ct.values, 0.0), sigma_0.values, atol=1e-11
    )


def test_unattainable_density_raises():
    # far denser than seawater at this salinity can be at the surface
    with pytest.raises(ValueError, match='not.*attainable'):
        ct_from_potential_density(1100.0, 35.0)


def test_nan_input_is_not_reported_as_unattainable():
    # below-bottom cells carry NaN and must pass through rather than
    # tripping the unattainable-density check
    sigma_0 = xr.DataArray(np.array([1026.5, np.nan]), dims=('nCells',))

    ct = ct_from_potential_density(sigma_0, 35.0)

    assert isinstance(ct, xr.DataArray)
    assert np.isfinite(ct.values[0])
    assert np.isnan(ct.values[1])
