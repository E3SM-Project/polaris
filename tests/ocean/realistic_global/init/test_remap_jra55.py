import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.remap_jra55 import (
    CARTESIAN_VAR_NAMES,
    cartesian_to_stress,
    check_no_missing_cells,
    stress_to_cartesian,
)


def _dataset(taux, tauy):
    return xr.Dataset(
        {
            'taux': ('nCells', np.asarray(taux, dtype=float)),
            'tauy': ('nCells', np.asarray(tauy, dtype=float)),
        }
    )


def test_fully_covered_cells_pass():
    """
    Bilinear weights cover a cell only to within round-off of one.
    """
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
    frac_b = np.array([1.0, 1.0 - 1.0e-15, 1.0 + 1.0e-15])
    check_no_missing_cells(ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b)


def test_an_uncovered_cell_raises():
    """
    ncremap writes zero to a cell the weights do not reach, so only the
    coverage from the mapping file shows it is missing.
    """
    ds = _dataset([1.0, 0.0, 3.0], [-1.0, 0.0, -3.0])
    frac_b = np.array([1.0, 0.0, 1.0])
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )


def test_a_partly_covered_cell_raises():
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
    frac_b = np.array([1.0, 0.5, 1.0])
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )


def test_a_non_finite_component_raises():
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, np.nan, -3.0])
    frac_b = np.ones(3)
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )


def test_cartesian_round_trip():
    """
    Rotating to Cartesian components and back at the same points recovers
    the zonal and meridional stress, and the vector stays tangent.
    """
    rng = np.random.default_rng(seed=0)
    lat = np.array([-89.5, -45.0, 0.0, 30.0, 89.5])
    lon = np.array([0.0, 90.0, 200.0, 359.0])
    ds = _lat_lon_dataset(
        lat,
        lon,
        taux=rng.normal(size=(lat.size, lon.size)),
        tauy=rng.normal(size=(lat.size, lon.size)),
    )

    ds_cart = stress_to_cartesian(ds)

    assert 'taux' not in ds_cart and 'tauy' not in ds_cart
    assert 'lat_bnds' in ds_cart and 'lon_bnds' in ds_cart
    lon_2d, lat_2d = np.meshgrid(np.deg2rad(lon), np.deg2rad(lat))
    radial = (
        ds_cart.tau_cart_x * np.cos(lat_2d) * np.cos(lon_2d)
        + ds_cart.tau_cart_y * np.cos(lat_2d) * np.sin(lon_2d)
        + ds_cart.tau_cart_z * np.sin(lat_2d)
    )
    assert radial.values == pytest.approx(0.0, abs=1e-12)

    ds_cells = xr.Dataset(
        {
            var: ('nCells', ds_cart[var].values.ravel())
            for var in CARTESIAN_VAR_NAMES
        }
    )
    ds_back = cartesian_to_stress(
        ds_cells, lon_cell=lon_2d.ravel(), lat_cell=lat_2d.ravel()
    )
    assert ds_back.taux.values == pytest.approx(ds.taux.values.ravel())
    assert ds_back.tauy.values == pytest.approx(ds.tauy.values.ravel())


def test_cartesian_average_keeps_a_vector_across_the_pole():
    """
    A uniform vector seen from opposite sides of the pole has opposite
    meridional components, so averaging the components cancels it.
    Averaging the Cartesian components keeps it.
    """
    lat = np.array([89.5])
    lon = np.array([0.0, 180.0])
    sin_lat = np.sin(np.deg2rad(lat[0]))
    # the tangent projection of the Cartesian vector (1, 0, 0)
    ds = _lat_lon_dataset(
        lat,
        lon,
        taux=np.array([[0.0, 0.0]]),
        tauy=np.array([[-sin_lat, sin_lat]]),
    )
    assert ds.tauy.mean().values == pytest.approx(0.0)

    ds_cart = stress_to_cartesian(ds).mean(dim='lon')
    ds_cells = xr.Dataset(
        {
            var: ('nCells', np.atleast_1d(ds_cart[var].values))
            for var in CARTESIAN_VAR_NAMES
        }
    )
    ds_pole = cartesian_to_stress(
        ds_cells,
        lon_cell=np.array([np.pi / 2.0]),
        lat_cell=np.array([np.deg2rad(89.9)]),
    )

    magnitude = np.hypot(ds_pole.taux.values, ds_pole.tauy.values)
    assert magnitude == pytest.approx(1.0, abs=1e-3)


def _lat_lon_dataset(lat, lon, taux, tauy):
    """Return a stress dataset on a lat-lon grid with bounds."""
    return xr.Dataset(
        {
            'taux': (('lat', 'lon'), taux, {'units': 'N m-2'}),
            'tauy': (('lat', 'lon'), tauy, {'units': 'N m-2'}),
            'lat_bnds': (('lat', 'nbnd'), np.stack([lat - 0.5, lat + 0.5], 1)),
            'lon_bnds': (('lon', 'nbnd'), np.stack([lon - 0.5, lon + 0.5], 1)),
        },
        coords={'lat': lat, 'lon': lon},
    )
