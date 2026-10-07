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
    compute_flux_forcing,
    compute_total_mass,
    cp_sw,
    rho_sw,
)
from polaris.ocean.model.ocean_model_step import (
    _elapsed_seconds,
    _expand_properties,
)


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


def _xtime_dataset(*times):
    xtime = np.array([t.encode() for t in times])
    return xr.Dataset({'xtime': ('Time', xtime)})


def test_elapsed_seconds_from_xtime():
    # MPAS-Ocean output without daysSinceStartOfSim carries times as xtime.
    # Selecting a single time slice first leaves a scalar that the string
    # parsing in polaris.mpas.time cannot walk, so the times have to come
    # from the whole dataset.
    ds = _xtime_dataset('0001-01-01_00:00:00', '0001-01-25_00:00:00')
    elapsed = _elapsed_seconds(ds, time_index_start=0, time_index_end=-1)
    assert elapsed == pytest.approx(24.0 * 86400.0)


def test_elapsed_seconds_from_days_since_start():
    ds = xr.Dataset({'daysSinceStartOfSim': ('Time', np.array([1.0, 10.0]))})
    assert _elapsed_seconds(ds, time_index_end=-1) == pytest.approx(
        10.0 * 86400.0
    )
    assert _elapsed_seconds(
        ds, time_index_start=0, time_index_end=-1
    ) == pytest.approx(9.0 * 86400.0)


def _evaporation_dataset(surface_temperatures, evaporation=1.0e-3):
    # one cell of unit area, two layers; only the top layer temperature
    # matters for the enthalpy carried by evaporation
    n_times = len(surface_temperatures)
    temperature = np.zeros((n_times, 1, 2))
    temperature[:, 0, 0] = surface_temperatures
    ds = xr.Dataset(
        {
            'temperature': (('Time', 'nCells', 'nVertLevels'), temperature),
            'evaporationFlux': (
                ('Time', 'nCells'),
                np.full((n_times, 1), evaporation),
            ),
        }
    )
    ds_mesh = xr.Dataset({'areaCell': ('nCells', np.ones(1))})
    return ds_mesh, ds


def test_enthalpy_uses_the_first_record_without_times():
    ds_mesh, ds = _evaporation_dataset([10.0, 20.0, 30.0])
    dt = 2.0 * 86400.0
    total = compute_flux_forcing(ds_mesh, ds, 'energy', dt, model='mpas-ocean')
    assert total == pytest.approx(1.0e-3 * cp_sw['mpas-ocean'] * 10.0 * dt)


def test_enthalpy_is_integrated_over_the_records_with_times():
    # the surface temperature rises linearly, so the trapezoidal rule is
    # exact and the integral uses the mean surface temperature of 20 C
    ds_mesh, ds = _evaporation_dataset([10.0, 20.0, 30.0])
    times = np.array([0.0, 1.0, 2.0]) * 86400.0
    dt = times[-1]
    total = compute_flux_forcing(
        ds_mesh, ds, 'energy', dt, model='mpas-ocean', times=times
    )
    assert total == pytest.approx(1.0e-3 * cp_sw['mpas-ocean'] * 20.0 * dt)


def test_enthalpy_starts_from_the_initial_condition():
    # Omega writes no output record at the start of the run, so the surface
    # temperature at time zero comes from the initial condition
    ds_mesh, ds = _evaporation_dataset([20.0, 30.0])
    _, ds_init = _evaporation_dataset([10.0])
    times = np.array([1.0, 2.0]) * 86400.0
    dt = times[-1]
    total = compute_flux_forcing(
        ds_mesh,
        ds,
        'energy',
        dt,
        model='omega',
        times=times,
        ds_init=ds_init,
    )
    assert total == pytest.approx(1.0e-3 * cp_sw['omega'] * 20.0 * dt)
