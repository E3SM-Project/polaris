"""
Unit tests for the overflow initial condition on the sigma coordinate.

The configs come from the task trees themselves, so the tests also check
that each tree layers its config files as intended.  The coordinate and the
initial density are built on a single row of cells across the slope, without
the Polaris step framework or file I/O.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.eos import compute_density
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.overflow import add_overflow_tasks
from polaris.tasks.ocean.overflow.init_utils import (
    compute_bottom_depth,
    compute_initial_density,
    compute_initial_temperature,
)

SIGMA_LEVELS = 64


def _tree_config(eos_type, coord_type):
    """The shared config of one overflow tree, plus the ocean defaults."""
    component = Ocean()
    add_overflow_tasks(component)
    filepath = f'ocean/planar/overflow/{eos_type}/{coord_type}/overflow.cfg'
    config = component.configs[filepath]
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    return component, config


def _make_ds(config):
    """
    Build the coordinate and the tracers on a row of cells spanning the
    shelf, the slope and the deep ocean, as the init step does.
    """
    lx = config.getfloat('overflow', 'lx')
    resolution = config.getfloat('overflow', 'resolution')
    x_cell = xr.DataArray(
        1.0e3 * np.arange(0.0, lx, resolution), dims=['nCells']
    )

    ds = xr.Dataset()
    ds['bottomDepth'] = compute_bottom_depth(config, x_cell)
    ds['ssh'] = xr.zeros_like(x_cell)
    init_vertical_coord(config, ds)

    temperature = compute_initial_temperature(config, x_cell)
    temperature = temperature.broadcast_like(ds.layerThickness)
    ds['temperature'] = temperature.transpose('Time', 'nCells', 'nVertLevels')
    salinity = config.getfloat('overflow', 'salinity')
    ds['salinity'] = salinity * xr.ones_like(ds.temperature)
    return ds


@pytest.mark.parametrize('eos_type', ['linear', 'nonlinear'])
def test_sigma_trees_are_added(eos_type):
    """
    Each sigma tree has the same tasks as the z-star tree, and its config
    selects the sigma coordinate without changing the geometric bathymetry.
    """
    component, config = _tree_config(eos_type, 'sigma')

    zstar_tasks = {
        path.split('/')[-1]
        for path in component.tasks
        if path.startswith('planar/overflow/linear/zstar/')
    }
    prefix = f'planar/overflow/{eos_type}/sigma/'
    sigma_tasks = {
        path.split('/')[-1]
        for path in component.tasks
        if path.startswith(prefix)
    }
    assert len(sigma_tasks) == 8
    assert sigma_tasks == zstar_tasks

    assert config.get('vertical_grid', 'coord_type') == 'sigma'
    assert config.getint('vertical_grid', 'vert_levels') == SIGMA_LEVELS
    assert config.getfloat('overflow', 'max_bottom_depth') == 2000.0


def test_sigma_layers_follow_bathymetry():
    """
    Every column uses every layer, and the uniform reference grid divides
    each column into equal layers, from the shelf to the deep ocean.
    """
    _, config = _tree_config('linear', 'sigma')
    ds = _make_ds(config)

    assert np.all(ds.minLevelCell == 1)
    assert np.all(ds.maxLevelCell == SIGMA_LEVELS)

    thickness = ds.layerThickness.isel(Time=0)
    expected = ds.bottomDepth / SIGMA_LEVELS
    assert np.max(np.abs(thickness - expected).values) < 1.0e-10

    # the columns really do span the shelf and the deep ocean
    assert ds.bottomDepth.min() < 501.0
    assert ds.bottomDepth.max() > 1999.0


def test_linear_zstar_density_is_unchanged():
    """
    Under the linear equation of state, the initial density ignores the
    pressure, so the z-star initial condition is bit-for-bit what it was
    before the pressure was computed.
    """
    _, config = _tree_config('linear', 'zstar')
    ds = _make_ds(config)

    density = compute_initial_density(config, ds)
    expected = compute_density(config, ds.temperature, ds.salinity)
    np.testing.assert_array_equal(density.values, np.asarray(expected))


def test_teos10_sigma_density_includes_compression():
    """
    Under TEOS-10, the initial density is evaluated at the hydrostatic
    pressure, so it increases down every column even though the tracers
    are uniform in the vertical.  Compression over 2000 m adds several
    kg m-3.
    """
    _, config = _tree_config('nonlinear', 'sigma')
    ds = _make_ds(config)

    density = compute_initial_density(config, ds).isel(Time=0)
    assert np.all(np.isfinite(density.values))
    assert np.all(density.diff('nVertLevels') > 0.0)

    higher_temperature = config.getfloat('overflow', 'higher_temperature')
    salinity = config.getfloat('overflow', 'salinity')
    surface_density = compute_density(
        config, higher_temperature, salinity, pressure=0.0
    )
    deep_column = int(ds.bottomDepth.argmax(dim='nCells'))
    compression = density.isel(nCells=deep_column) - surface_density
    assert 0.0 < compression.isel(nVertLevels=0) < 0.2
    assert 5.0 < compression.isel(nVertLevels=-1) < 15.0
