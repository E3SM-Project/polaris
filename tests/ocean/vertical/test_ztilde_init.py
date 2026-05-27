"""
Unit tests for ZTildeInitStep.

All tests are self-contained: no file I/O, no full Polaris step framework.
A minimal ConfigParser and xarray.Dataset are constructed in each test.
"""

import logging
from configparser import ConfigParser

import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import RhoSw
from polaris.ocean.vertical.ztilde_init import ZTildeInitStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    rhoref=None, iter_count=10, partial_cell_type=None, bottom_depth=600.0
):
    """Return a minimal ConfigParser for ZTildeInitStep tests.

    Parameters
    ----------
    bottom_depth : float
        Reference pseudo-depth of the grid (m).  Must be >= the target
        geometric depth used in the test so the coordinate is not capped.
    """
    if rhoref is None:
        rhoref = RhoSw

    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', '4')
    # bottom_depth rescales uniform grid from [0,1] to [0, bottom_depth]
    config.set('vertical_grid', 'bottom_depth', str(bottom_depth))
    config.set('vertical_grid', 'min_vert_levels', '1')
    config.set('vertical_grid', 'min_layer_thickness', '0.0')
    config.set('vertical_grid', 'pseudothickness_iter_count', str(iter_count))
    config.set(
        'vertical_grid',
        'water_col_adjust_frac_change_threshold',
        '1e-12',
    )
    if partial_cell_type is not None:
        config.set('vertical_grid', 'partial_cell_type', partial_cell_type)
        config.set('vertical_grid', 'min_pc_fraction', '0.1')

    config.add_section('ocean')
    config.set('ocean', 'eos_type', 'constant')
    config.set('ocean', 'eos_constant_rhoref', str(rhoref))

    return config


def _make_ds_mesh(ncells=1):
    """Return a minimal horizontal mesh dataset with nCells dimension."""
    return xr.Dataset(
        {'xCell': xr.DataArray(np.zeros(ncells), dims=['nCells'])}
    )


def _make_step(cls, config, logger=None):
    """Bypass the Polaris Step constructor and set the bare minimum attrs."""
    step = object.__new__(cls)
    step.config = config
    step.logger = logger or logging.getLogger('test_ztilde_init')
    return step


class _ConstantTracerStep(ZTildeInitStep):
    """Minimal concrete subclass that returns constant CT and SA."""

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        ncells = ds.sizes['nCells']
        nvertlevels = ds.sizes['nVertLevels']
        shape = (1, ncells, nvertlevels)
        ct = xr.DataArray(
            data=np.full(shape, 10.0),
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        sa = xr.DataArray(
            data=np.full(shape, 35.0),
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        return ct, sa


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_abstract_class_not_instantiable():
    """ZTildeInitStep itself cannot be instantiated (init_tracers is abstract).

    The test checks __abstractmethods__ directly so no Polaris component mock
    is needed.
    """
    assert 'init_tracers' in ZTildeInitStep.__abstractmethods__


def test_subclass_without_init_tracers_not_instantiable():
    """A subclass that does not implement init_tracers raises TypeError."""

    class _Missing(ZTildeInitStep):
        pass

    assert 'init_tracers' in _Missing.__abstractmethods__


def test_minimal_subclass_returns_complete_dataset():
    """A constant-tracer subclass completes without error and the returned
    dataset contains all expected base-class output variables.
    """
    config = _make_config()
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -500.0), dims=['nCells'])

    ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    required = [
        'temperature',
        'salinity',
        'SpecVol',
        'pressure',
        'GeomZMid',
        'GeomZInterface',
        'bottomDepth',
        'SurfacePressure',
        'BottomPressure',
        'PseudoThickness',
        'ZTildeMid',
        'ZTildeInterface',
        'cellMask',
        'minLevelCell',
        'maxLevelCell',
        'RefPseudoThickness',
        'vertCoordMovementWeights',
    ]
    for var in required:
        assert var in ds, f'{var!r} missing from output dataset'


def test_constant_density_converges_cleanly(caplog):
    """With rhoref = RhoSw the initial guess is exact.

    The loop should exit via the convergence check (not a stagnation warning)
    and bottomDepth should equal the target to within floating-point precision.
    """
    target_depth = 500.0
    # bottom_depth == target_depth: reference grid exactly matches the column
    config = _make_config(rhoref=RhoSw, bottom_depth=target_depth)
    step = _make_step(_ConstantTracerStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])

    with caplog.at_level(logging.WARNING, logger='test_ztilde_init'):
        ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    # No stagnation warning should appear for a perfect initial guess
    assert 'full-cell snap' not in caplog.text

    bottom_depth = float(ds.bottomDepth.values.flat[0])
    np.testing.assert_allclose(bottom_depth, target_depth, rtol=1e-10)


def test_wrong_reference_density_requires_multiple_iterations():
    """When rhoref != RhoSw the first iteration produces a non-unit scaling
    factor and multiple iterations are needed before the convergence check
    fires.  The final bottomDepth should match the target to within the
    convergence threshold times the target depth.
    """
    # 1% denser than the reference → scaling ≠ 1 on first iteration
    rhoref = RhoSw * 1.01
    config = _make_config(rhoref=rhoref)
    step = _make_step(_ConstantTracerStep, config)

    target_depth = 500.0
    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -target_depth), dims=['nCells'])

    ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    bottom_depth = float(ds.bottomDepth.values.flat[0])
    # Converged bottomDepth must be within the fractional threshold of target
    threshold = 1e-12
    np.testing.assert_allclose(bottom_depth, target_depth, rtol=threshold * 10)


def test_full_cell_stagnation_warning_and_early_exit(caplog):
    """When _build_vert_coord_ds always returns the same BottomPressure
    (simulating full-cell snapping) the stagnation check should fire and the
    loop should stop with a warning, without raising an exception.
    """

    class _StagnantStep(_ConstantTracerStep):
        """Override _build_vert_coord_ds to snap to a fixed pressure."""

        def _build_vert_coord_ds(
            self,
            ds_mesh: xr.Dataset,
            bottom_pressure: xr.DataArray,
        ) -> xr.Dataset:
            # Call the real coord builder once to get a properly structured ds
            ds = super()._build_vert_coord_ds(ds_mesh, bottom_pressure)
            # Then hard-code BottomPressure to a fixed value regardless of
            # the incoming bottom_pressure (full-cell snapping simulation)
            fixed_pressure = xr.DataArray(
                np.full(ds_mesh.sizes['nCells'], 5.0e6),
                dims=['nCells'],
            )
            ds['BottomPressure'] = fixed_pressure
            return ds

    config = _make_config(iter_count=10)
    step = _make_step(_StagnantStep, config)

    ncells = 1
    ds_mesh = _make_ds_mesh(ncells)
    geom_z_bot = xr.DataArray(np.full(ncells, -500.0), dims=['nCells'])

    with caplog.at_level(logging.WARNING, logger='test_ztilde_init'):
        ds = step.run_z_tilde_init(ds_mesh, geom_z_bot)

    assert 'full-cell snap' in caplog.text
    # Must still return a usable dataset
    assert 'bottomDepth' in ds
