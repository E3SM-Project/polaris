"""
Unit tests for the seamount vertical coordinate as Omega sees it.

The seamount builds a geometric coordinate (sigma or z-star) and relies on
Polaris converting it to pseudo-height for Omega, rather than on any
p-star-specific initialization.  These tests exercise that path directly:
build the coordinate on a seamount-like set of columns, convert it with
``pseudothickness_from_ds()``, and check the two properties the test case
depends on.

All tests are self-contained: no file I/O, no full Polaris step framework.
"""

from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.eos import compute_linear_density
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.diagnostics import pseudothickness_from_ds
from polaris.ocean.vertical.ztilde import Gravity, RhoSw

# Beckmann and Haidvogel exponential stratification, as configured for the
# seamount, together with the linear EOS parameters it is inverted through
DENSITY_COEF = 1028.0
DENSITY_GRADIENT = 3.0
DENSITY_DEPTH = 500.0
EOS_RHOREF = 1001.0
EOS_ALPHA = 0.2
EOS_BETA = 0.8
SALINITY = 35.0

MAX_BOTTOM_DEPTH = 5000.0
SEAMOUNT_HEIGHT = 4500.0
SEAMOUNT_WIDTH = 40.0e3
VERT_LEVELS = 32


def _make_config(coord_type, partial_cell_type='None'):
    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', str(VERT_LEVELS))
    config.set('vertical_grid', 'bottom_depth', str(MAX_BOTTOM_DEPTH))
    config.set('vertical_grid', 'coord_type', coord_type)
    config.set('vertical_grid', 'partial_cell_type', partial_cell_type)
    config.set('vertical_grid', 'min_pc_fraction', '0.1')
    config.set('vertical_grid', 'min_vert_levels', '1')
    config.set('vertical_grid', 'min_layer_thickness', '0.0')
    config.set('vertical_grid', 'pseudothickness_iter_count', '10')

    config.add_section('ocean')
    config.set('ocean', 'eos_type', 'linear')
    config.set('ocean', 'eos_linear_rhoref', str(EOS_RHOREF))
    config.set('ocean', 'eos_linear_alpha', str(EOS_ALPHA))
    config.set('ocean', 'eos_linear_beta', str(EOS_BETA))
    config.set('ocean', 'eos_linear_Tref', '0.0')
    config.set('ocean', 'eos_linear_Sref', '0.0')
    return config


def _bottom_depth(flat):
    """Seamount bathymetry, or a flat floor for the negative control."""
    radius = np.linspace(0.0, 160.0e3, 24)
    if flat:
        return MAX_BOTTOM_DEPTH * np.ones_like(radius)
    return MAX_BOTTOM_DEPTH - SEAMOUNT_HEIGHT * np.exp(
        -(radius**2) / SEAMOUNT_WIDTH**2
    )


def _make_ds(config, flat=False):
    """Build the geometric coordinate and the seamount tracer profile."""
    ds = xr.Dataset()
    ds['bottomDepth'] = xr.DataArray(_bottom_depth(flat), dims=['nCells'])
    ds['ssh'] = xr.zeros_like(ds.bottomDepth)
    init_vertical_coord(config, ds)

    density = DENSITY_COEF - DENSITY_GRADIENT * np.exp(
        ds.zMid.squeeze('Time') / DENSITY_DEPTH
    )
    ds['salinity'] = SALINITY * xr.ones_like(density)
    ds['temperature'] = (
        EOS_RHOREF + EOS_BETA * ds.salinity - density
    ) / EOS_ALPHA
    return ds


def _pseudo_interface_pressure(ds, config):
    """
    Convert the geometric coordinate to pseudo-thickness the way Polaris
    does when writing an Omega initial condition, then integrate gauge
    pressure down the column.
    """
    pseudo_thickness, _ = pseudothickness_from_ds(
        ds, config=config, src_var_name='restingThickness', surf_pressure=0.0
    )
    assert pseudo_thickness is not None
    h_tilde = np.nan_to_num(pseudo_thickness.values)
    if h_tilde.ndim == 3:
        h_tilde = h_tilde[0]
    zeros = np.zeros((h_tilde.shape[0], 1))
    return (
        RhoSw
        * Gravity
        * np.cumsum(np.concatenate([zeros, h_tilde], axis=1), axis=1)
    )


def test_temperature_reproduces_target_density():
    """
    The back-solve through the full linear EOS, including the salinity
    term, must reproduce the Beckmann and Haidvogel density profile.
    """
    config = _make_config('sigma')
    ds = _make_ds(config)

    density = compute_linear_density(config, ds.temperature, ds.salinity)
    target = DENSITY_COEF - DENSITY_GRADIENT * np.exp(
        ds.zMid.squeeze('Time') / DENSITY_DEPTH
    )
    assert np.nanmax(np.abs(density - target).values) < 1.0e-10


@pytest.mark.parametrize(
    'coord_type,partial_cell_type',
    [('sigma', 'None'), ('z-star', 'partial')],
)
def test_geometric_round_trip(coord_type, partial_cell_type):
    """
    Converting the geometric coordinate to pseudo-thickness and back must
    recover the geometric column thickness.  This is the property Omega
    relies on when it anchors the column at BottomGeomDepth.
    """
    config = _make_config(coord_type, partial_cell_type)
    ds = _make_ds(config)

    pseudo_thickness, spec_vol = pseudothickness_from_ds(
        ds, config=config, src_var_name='restingThickness', surf_pressure=0.0
    )
    assert pseudo_thickness is not None and spec_vol is not None

    geom = (spec_vol * pseudo_thickness * RhoSw).fillna(0.0)
    column = geom.sum(dim='nVertLevels')
    assert np.max(np.abs(column - ds.bottomDepth).values) < 1.0e-8


def test_sigma_layers_are_proportional_to_column_depth():
    """
    Sigma must be exactly terrain-following in geometric height: every
    column devotes the same fraction of its depth to each layer.
    """
    config = _make_config('sigma')
    ds = _make_ds(config)

    thickness = ds.restingThickness.squeeze('Time').values
    fraction = thickness / ds.bottomDepth.values[:, None]
    spread = fraction.max(axis=0) - fraction.min(axis=0)
    assert np.max(spread) < 1.0e-12


def test_sigma_interior_interfaces_tilt():
    """
    Interior interfaces must sit at genuinely different pressures from one
    column to the next.  A coordinate that clipped a shared reference grid
    at the seafloor instead of stretching to it would put every interior
    interface at the same pressure, leaving the whole pressure-gradient
    signal in the bottom cell.
    """
    config = _make_config('sigma')
    ds = _make_ds(config)

    pressure = _pseudo_interface_pressure(ds, config)
    interior = pressure[:, 1:-1]
    relative_rms = np.std(interior, axis=0) / np.mean(interior, axis=0)
    assert np.min(relative_rms) > 1.0e-3


def test_flat_bottom_interfaces_do_not_tilt():
    """
    The negative control for :py:func:`test_sigma_interior_interfaces_tilt`.
    With a flat floor there is nothing for sigma to follow, so the same
    measurement must come back at round-off.  Without this, a tilt check
    that could never fail would look like it was protecting something.
    """
    config = _make_config('sigma')
    ds = _make_ds(config, flat=True)

    pressure = _pseudo_interface_pressure(ds, config)
    interior = pressure[:, 1:-1]
    relative_rms = np.std(interior, axis=0) / np.mean(interior, axis=0)
    assert np.max(relative_rms) < 1.0e-12
