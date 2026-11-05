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
    compute_energy_change,
    compute_total_energy,
    compute_total_mass,
    cp_sw,
    rho_sw,
)
from polaris.ocean.model.ocean_model_step import (
    OceanModelStep,
    _elapsed_seconds,
    _expand_properties,
)


@pytest.mark.parametrize(
    'model, thickness',
    [('omega', 'pseudoThickness'), ('mpas-ocean', 'layerThickness')],
)
@pytest.mark.parametrize('baseline', ['init', 'output'])
def test_energy_error_below_total_float64_spacing(model, thickness, baseline):
    mesh = xr.Dataset({'areaCell': ('nCells', [1.0])})
    start = xr.Dataset(
        {
            thickness: (('nCells', 'nVertLevels'), [[1.0, 1.0]]),
            'temperature': (('nCells', 'nVertLevels'), [[1.0, 0.001]]),
        }
    )
    end = start.copy(deep=True)
    end.temperature.values[0, 1] = np.nextafter(0.001, np.inf)
    delta_t = end.temperature.values[0, 1] - 0.001
    expected = rho_sw * cp_sw[model] * delta_t
    assert float(compute_total_energy(mesh, end, model)) == float(
        compute_total_energy(mesh, start, model)
    )
    assert float(
        compute_energy_change(mesh, start, end, model)
    ) == pytest.approx(expected, rel=1e-12, abs=0.0)
    output = xr.concat([start, end], dim='Time')
    step = OceanModelStep.__new__(OceanModelStep)
    error = step._compute_rel_err(
        compute_total_energy,
        ds_mesh=mesh,
        ds=output,
        ds_init=start.expand_dims('Time') if baseline == 'init' else None,
        time_index_end=-1,
        model=model,
    )
    assert error > 0
    assert error == pytest.approx(delta_t / 1.001, rel=1e-12, abs=0.0)
    assert f'{error:.6e}' != '0.000000e+00'


def test_energy_change_includes_thickness_and_temperature():
    mesh, start = _mesh_and_state()
    start['temperature'] = xr.ones_like(start.layerThickness)
    end = start.copy(deep=True)
    end['temperature'] = 2.0 * start.temperature
    end['layerThickness'] = 3.0 * start.layerThickness
    expected = 5.0 * float(compute_total_energy(mesh, start, 'omega'))
    assert float(
        compute_energy_change(mesh, start, end, 'omega')
    ) == pytest.approx(expected)
    assert float(compute_energy_change(mesh, start, start, 'omega')) == 0.0


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
