"""
The finite-volume kernel with the parabolic reconstruction.

The parabolic reconstruction widens the exact set from profiles linear in
pressure to profiles quadratic in it, so what the ``_linear`` variants pin for
the linear reconstruction is pinned here on the ``_quadratic`` ones: the
matched-pressure integrand is zero at every quadrature point, and the column
scan stays flat, including over a bathymetry step where one column's parabola
is extrapolated below its own floor.
"""

import numpy as np
import pytest

from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    column_scan,
    delta_specvol_at_pressure,
    finite_volume_hpga,
    hydrostatic_scale,
    matched_pressure_pieces,
)

from .two_column import (
    LINEAR_VARIANT,
    QUADRATIC_VARIANT,
    STEP_QUADRATIC_VARIANT,
    build_state,
    sweep,
)

# The tolerances of test_matched_pressure.py, for the same quantities.
_ROUNDOFF_TOL = 1.0e-14
_POINTWISE_TOL = 1.0e-14
_NODES, _ = np.polynomial.legendre.leggauss(4)


def _worst_pointwise(pieces) -> tuple[float, float]:
    """The largest ``|[dalpha]|`` at any quadrature point, and its scale."""
    scale = float(np.abs(pieces['expansion'].alpha_theta).max()) * float(
        np.nanmax(pieces['theta']) - np.nanmin(pieces['theta'])
    )
    edges = pieces['edge_interface']
    worst = 0.0
    for edge_layer in range(int(min(pieces['deepest'])) + 1):
        top, bot = edges[edge_layer], edges[edge_layer + 1]
        pressure = 0.5 * (top + bot) + 0.5 * (bot - top) * _NODES
        contrast = delta_specvol_at_pressure(pieces, edge_layer, pressure)
        worst = max(worst, float(np.max(np.abs(contrast))))
    return worst, scale


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt',
    [(QUADRATIC_VARIANT, *point) for point in sweep(QUADRATIC_VARIANT)]
    + [(LINEAR_VARIANT, 4.0, 64.0, 50.0)],
)
def test_parabolic_integrand_is_pointwise_zero_on_its_exact_set(
    variant, horiz_res, vert_res, tilt
):
    """``[dalpha]`` vanishes at every point for a profile quadratic in p.

    The same property, for the same reason, as the linear reconstruction has
    on a profile linear in pressure: two mean-preserving parabolas built on
    different interfaces from different layer means recover the identical
    profile, so the two columns describe the same water at every pressure.  A
    linear profile is in this exact set too.
    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    pieces = matched_pressure_pieces(ds, vertical_reconstruction='ppm')
    worst, scale = _worst_pointwise(pieces)

    assert worst <= _POINTWISE_TOL * scale, (
        f'{variant} {vert_res} m, tilt {tilt} m/km: max |Delta_e alpha| = '
        f'{worst:.3e} m3 kg-1, more than {_POINTWISE_TOL * scale:.3e}'
    )


@pytest.mark.parametrize('vert_res, tilt', [(256.0, 0.05), (64.0, 50.0)])
def test_linear_integrand_is_not_zero_on_a_quadratic_profile(vert_res, tilt):
    """The quadratic variants are outside the linear reconstruction's set.

    Without this the test above could pass because the variant had quietly
    become linear, or untilted.
    """
    ds = build_state(QUADRATIC_VARIANT, 4.0, vert_res, tilt)
    worst, scale = _worst_pointwise(matched_pressure_pieces(ds))

    assert worst > 1.0e3 * _POINTWISE_TOL * scale, (
        f'{vert_res} m, tilt {tilt} m/km: the linear reconstruction leaves '
        f'only {worst:.3e} m3 kg-1 on a quadratic profile'
    )


@pytest.mark.parametrize('vert_res, tilt', [(256.0, 0.05), (64.0, 50.0)])
def test_parabolic_scan_stays_flat_on_a_tilted_coordinate(vert_res, tilt):
    """``D_k`` is the anchor's value at every interface, to round-off."""
    ds = build_state(QUADRATIC_VARIANT, 4.0, vert_res, tilt)
    difference = column_scan(
        matched_pressure_pieces(ds, vertical_reconstruction='ppm')
    )

    worst = float(np.ptp(difference))
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert worst <= tolerance, (
        f'{vert_res} m, tilt {tilt} m/km: D_k varies by {worst:.3e} m down '
        f'the column, more than {tolerance:.3e} m'
    )


@pytest.mark.parametrize('tilt', [1.0, 25.0, 100.0, 200.0])
def test_parabolic_scan_stays_flat_over_a_bathymetry_step(tilt):
    """Assumption A5 with the parabola extrapolated below a column's floor.

    ``bathymetry_step_quadratic`` is inside the parabolic reconstruction's
    exact set and has a stepped sea floor.  At 100 and 200 m/km the deepest
    edge layers evaluate one column's bottom parabola two and three layers
    below its own floor; an extrapolated parabola still reproduces the
    quadratic it resolves, so the scan stays flat regardless.
    """
    ds = build_state(STEP_QUADRATIC_VARIANT, 4.0, 256.0, tilt)
    difference = column_scan(
        matched_pressure_pieces(ds, vertical_reconstruction='ppm')
    )

    worst = float(np.ptp(difference))
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert worst <= tolerance, (
        f'grad={tilt} m/km: D_k varies by {worst:.3e} m down the column, more '
        f'than {tolerance:.3e} m, so the below-floor extrapolation is '
        'breaking the cancellation'
    )


def test_parabolic_and_linear_agree_on_a_linear_profile():
    """Both reconstructions resolve a linear profile, so they agree there.

    What remains of either is the anchor, which describes the same water with
    both reconstructions.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 64.0, 50.0)
    linear = finite_volume_hpga(ds, dx=4.0e3).isel(Time=0).values
    parabolic = (
        finite_volume_hpga(ds, dx=4.0e3, vertical_reconstruction='ppm')
        .isel(Time=0)
        .values
    )
    valid = np.isfinite(linear)
    scale = float(np.sqrt(np.mean(linear[valid] ** 2)))
    np.testing.assert_allclose(
        parabolic[valid], linear[valid], rtol=0.0, atol=1.0e-6 * scale
    )


def test_linear_is_the_default_and_unchanged():
    """Asking for nothing is asking for the linear reconstruction."""
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    default = finite_volume_hpga(ds, dx=4.0e3).values
    linear = finite_volume_hpga(
        ds, dx=4.0e3, vertical_reconstruction='linear'
    ).values
    np.testing.assert_array_equal(default, linear)
    np.testing.assert_array_equal(default, ds.HPGAFiniteVolume.values)
    assert matched_pressure_pieces(ds)['curvature_theta'] is None


def test_init_writes_the_parabolic_hpga():
    """``init.nc`` carries the field Omega's ppm output is compared against."""
    ds = build_state(QUADRATIC_VARIANT, 4.0, 256.0, 50.0)
    expected = finite_volume_hpga(
        ds, dx=4.0e3, vertical_reconstruction='ppm'
    ).values
    np.testing.assert_array_equal(ds.HPGAFiniteVolumePPM.values, expected)


def test_unknown_vertical_reconstruction_is_rejected():
    """A typo must not silently run the linear reconstruction."""
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    with pytest.raises(ValueError, match='vertical reconstruction'):
        matched_pressure_pieces(ds, vertical_reconstruction='weno')
