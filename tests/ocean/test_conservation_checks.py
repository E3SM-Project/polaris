"""
Tests for expanding a ``tracer conservation`` check into one check per
tracer.

A single ``tracer`` check used to be hard-wired to ``tracer1``, so tasks such
as ``sphere_transport`` that transport several tracers silently checked only
the first of them.
"""

import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.conservation import (
    TRACERS_TO_CHECK,
    compute_total_mass,
    rho_sw,
)
from polaris.ocean.model.ocean_model_step import _expand_properties


def _make_dataset(*tracer_names):
    return xr.Dataset({name: ('nCells', np.zeros(4)) for name in tracer_names})


def test_non_tracer_properties_pass_through():
    ds = _make_dataset('tracer1')
    assert _expand_properties(['mass', 'energy'], ds) == [
        ('mass', None),
        ('energy', None),
    ]


def test_tracer_expands_to_every_tracer_present():
    ds = _make_dataset('temperature', 'salinity', 'tracer1', 'tracer3')
    assert _expand_properties(['tracer'], ds) == [
        ('tracer', 'temperature'),
        ('tracer', 'salinity'),
        ('tracer', 'tracer1'),
        ('tracer', 'tracer3'),
    ]


def test_tracers_absent_from_the_output_are_skipped():
    ds = _make_dataset('tracer1')
    assert _expand_properties(['tracer'], ds) == [('tracer', 'tracer1')]


def test_expansion_is_in_the_declared_tracer_order():
    ds = _make_dataset(*reversed(TRACERS_TO_CHECK))
    expanded = _expand_properties(['tracer'], ds)
    assert [tracer for _, tracer in expanded] == TRACERS_TO_CHECK


def test_a_dataset_with_no_tracers_yields_no_checks():
    ds = _make_dataset('layerThickness')
    assert _expand_properties(['tracer'], ds) == []


def test_mixed_properties_keep_their_order():
    ds = _make_dataset('tracer1', 'tracer2')
    assert _expand_properties(['mass', 'tracer'], ds) == [
        ('mass', None),
        ('tracer', 'tracer1'),
        ('tracer', 'tracer2'),
    ]


def test_conservation_can_be_imported_on_its_own():
    # polaris.ocean.conservation must not pull in polaris.ocean.model at
    # module scope: that package imports the step classes, which import this
    # module back, so the import only works when something else happens to
    # import polaris.ocean.model first
    code = 'import polaris.ocean.conservation'
    subprocess.run(
        [sys.executable, '-c', code], check=True, capture_output=True
    )


def _mesh_and_state(n_times=None):
    ds_mesh = xr.Dataset({'areaCell': ('nCells', np.full(3, 2.0))})
    dims: tuple[str, ...] = ('nCells', 'nVertLevels')
    shape: tuple[int, ...] = (3, 4)
    if n_times is not None:
        dims = ('Time',) + dims
        shape = (n_times,) + shape
    ds = xr.Dataset({'layerThickness': (dims, np.full(shape, 10.0))})
    return ds_mesh, ds


def test_a_single_time_slice_is_accepted():
    ds_mesh, ds = _mesh_and_state(n_times=2)
    total = compute_total_mass(ds_mesh, ds.isel(Time=0))
    # 3 cells * 2 m^2 * 4 layers * 10 m * rho_sw
    assert float(total) == pytest.approx(240.0 * rho_sw)


def test_a_dataset_with_no_time_dimension_is_accepted():
    ds_mesh, ds = _mesh_and_state()
    assert float(compute_total_mass(ds_mesh, ds)) == pytest.approx(
        240.0 * rho_sw
    )


def test_more_than_one_time_slice_is_rejected():
    # silently using the last time slice would give a conservation number
    # for a state the caller did not ask about
    ds_mesh, ds = _mesh_and_state(n_times=2)
    with pytest.raises(ValueError, match='single time slice'):
        compute_total_mass(ds_mesh, ds)
