from configparser import ConfigParser

import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.tasks.ocean.realistic_global.init.viz import _add_layer_thickness


def _eos_config():
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'eos_type', 'teos-10')
    return config


def test_omega_initial_state_gets_a_geometric_layer_thickness():
    """
    Omega's initial state has a pseudo-thickness and no specific volume, so
    the geometric thickness the plots need comes from the equation of state.
    """
    cell_dims = ('nCells', 'nVertLevels')
    ds = xr.Dataset(
        data_vars=dict(
            temperature=(cell_dims, [[10.0, 5.0, 2.0]]),
            salinity=(cell_dims, [[34.0, 34.5, 35.0]]),
            SurfacePressure=('nCells', [1.0e4]),
            PseudoThickness=(cell_dims, [[10.0, 100.0, 1000.0]]),
        )
    )

    ds = _add_layer_thickness(ds, _eos_config())

    rho_sw = get_constant('seawater_density_reference')
    expected = rho_sw * ds.SpecVol * ds.PseudoThickness
    np.testing.assert_allclose(ds.layerThickness, expected)
    # seawater is denser than the reference, but not by much
    ratio = ds.layerThickness / ds.PseudoThickness
    assert np.all((ratio > 0.99) & (ratio < 1.01))


def test_mpas_ocean_initial_state_is_left_alone():
    """MPAS-Ocean's initial state carries its layer thickness already."""
    ds = xr.Dataset(
        data_vars=dict(
            layerThickness=(('nCells', 'nVertLevels'), [[10.0, 100.0]])
        )
    )
    assert _add_layer_thickness(ds, _eos_config()) is ds
    assert 'SpecVol' not in ds
