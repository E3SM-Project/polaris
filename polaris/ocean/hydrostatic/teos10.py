r"""
Hydrostatic integration utilities for the Omega ocean model.

This module currently provides functionality for converting from the
Omega pseudo-height coordinate :math:`\tilde z` (``z_tilde``) to true
geometric height ``z`` by numerically integrating the hydrostatic
relation

.. math::

    \frac{\partial z}{\partial \tilde z} = \rho_0\,\nu( S_A, \Theta, p )

where :math:`\nu` is the specific volume (``spec_vol``) computed from the
TEOS-10 equation of state, :math:`S_A` is Absolute Salinity, :math:`\Theta`
is Conservative Temperature, :math:`p` is sea pressure (positive downward),
and :math:`\rho_0` is a reference density used in the definition of
``z_tilde = - p / (\rho_0 g)`.  The conversion therefore requires an
integral of the form

.. math::

    z(\tilde z) = z_b + \int_{\tilde z_b}^{\tilde z}
    \rho_0\,\nu\big(S_A(\tilde z'),\Theta(\tilde z'),p(\tilde z')\big)\;
    d\tilde z' ,

with :math:`z_b = -\text{bottom\_depth}` at the pseudo-height
``z_tilde_b`` at the seafloor, typically the minimum (most negative) value
of the pseudo-height domain for a given water column.

The primary entry point is :func:`integrate_geometric_height`.
"""

from __future__ import annotations

from typing import Callable, Literal, Sequence

import gsw
import numpy as np
from mpas_tools.cime.constants import constants

__all__ = [
    'integrate_geometric_height',
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def integrate_geometric_height(
    z_tilde_interfaces: Sequence[float] | np.ndarray,
    z_tilde_nodes: Sequence[float] | np.ndarray,
    sa_nodes: Sequence[float] | np.ndarray,
    ct_nodes: Sequence[float] | np.ndarray,
    bottom_depth: float,
    rho0: float,
    method: Literal[
        'midpoint', 'trapezoid', 'simpson', 'gauss2', 'gauss4', 'adaptive'
    ] = 'gauss4',
    subdivisions: int = 2,
    rel_tol: float = 5e-8,
    abs_tol: float = 5e-5,
    max_recurs_depth: int = 12,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Integrate the hydrostatic relation to obtain geometric height.

    Integrates upward from the seafloor using
    ``dz/dz_tilde = rho0 * spec_vol(SA, CT, p)`` to obtain geometric
    heights ``z`` at requested pseudo-heights ``z_tilde_interfaces``.

    The salinity and temperature profiles are supplied as *piecewise
    linear* functions of pseudo-height via collocation nodes and their
    values. Outside the node range, profiles are held constant at the
    end values (``numpy.interp`` behavior), permitting targets to extend
    above or below the collocation range.

    Methods
    -------
    The integral over each interface interval can be evaluated with one of
    the following schemes (set with ``method``):

    - 'midpoint': composite midpoint rule with ``subdivisions`` panels.
    - 'trapezoid': composite trapezoidal rule with ``subdivisions`` panels.
    - 'simpson': composite Simpson's rule; requires an even number of
        panels. If ``subdivisions`` is odd, one is added internally.
    - 'gauss2': 2-point Gauss-Legendre per panel (higher accuracy than
        midpoint/trapezoid at similar cost).
    - 'gauss4': 4-point Gauss-Legendre per panel (default; high accuracy
        for smooth integrands).
    - 'adaptive': adaptive recursive Simpson integration controlled by
        ``rel_tol``, ``abs_tol`` and ``max_depth``.

    Parameters
    ----------
    z_tilde_interfaces : sequence of float
        Monotonic non-increasing layer-interface pseudo-heights ordered
        from sea surface to seafloor. The first value corresponds to the
        sea surface (typically near 0) and the last to the seafloor
        (most negative). Values may extend outside the node range.
    z_tilde_nodes : sequence of float
        Strictly increasing collocation nodes for SA and CT.
    sa_nodes, ct_nodes : sequence of float
        Absolute Salinity (g/kg) and Conservative Temperature (degC) at
        ``z_tilde_nodes``.
    bottom_depth : float
        Positive depth (m); geometric height at seafloor is ``-bottom_depth``.
    rho0 : float
        Reference density used in the pseudo-height definition.
    method : str, optional
        Quadrature method ('midpoint','trapezoid','simpson','gauss2',
        'gauss4','adaptive'). Default 'gauss4'.
    subdivisions : int, optional
        Subdivisions per interval for fixed-step methods (>=1). Ignored
        for 'adaptive'.
    rel_tol, abs_tol : float, optional
        Relative/absolute tolerances for adaptive Simpson.
    max_recurs_depth : int, optional
        Max recursion depth for adaptive Simpson.

    Returns
    -------
    z : ndarray
        Geometric heights at ``z_tilde_interfaces``.
    spec_vol : ndarray
        Specific volume at targets.
    ct : ndarray
        Conservative temperature at targets.
    sa : ndarray
        Absolute salinity at targets.
    """

    z_tilde_interfaces = np.asarray(z_tilde_interfaces, dtype=float)
    z_tilde_nodes = np.asarray(z_tilde_nodes, dtype=float)
    sa_nodes = np.asarray(sa_nodes, dtype=float)
    ct_nodes = np.asarray(ct_nodes, dtype=float)

    if not (
        z_tilde_nodes.ndim == sa_nodes.ndim == ct_nodes.ndim == 1
        and z_tilde_interfaces.ndim == 1
    ):
        raise ValueError('All inputs must be one-dimensional.')
    if len(z_tilde_nodes) != len(sa_nodes) or len(z_tilde_nodes) != len(
        ct_nodes
    ):
        raise ValueError(
            'Lengths of z_tilde_nodes, sa_nodes, ct_nodes differ.'
        )
    if len(z_tilde_nodes) < 2:
        raise ValueError('Need at least two collocation nodes.')
    if not np.all(np.diff(z_tilde_nodes) > 0):
        raise ValueError('z_tilde_nodes must be strictly increasing.')
    if not np.all(np.diff(z_tilde_interfaces) <= 0):
        raise ValueError('z_tilde_interfaces must be non-increasing.')
    if subdivisions < 1:
        raise ValueError('subdivisions must be >= 1.')

    g = constants['SHR_CONST_G']

    def spec_vol_ct_sa_at(
        z_tilde: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sa = np.interp(z_tilde, z_tilde_nodes, sa_nodes)
        ct = np.interp(z_tilde, z_tilde_nodes, ct_nodes)
        p_pa = -rho0 * g * z_tilde
        # gsw expects pressure in dbar
        spec_vol = gsw.specvol(sa, ct, p_pa * 1.0e-4)
        return spec_vol, ct, sa

    def integrand(z_tilde: np.ndarray) -> np.ndarray:
        spec_vol, _, _ = spec_vol_ct_sa_at(z_tilde)
        return rho0 * spec_vol

    # fill interface heights: anchor bottom, integrate upward (reverse)
    n_interfaces = len(z_tilde_interfaces)
    if n_interfaces < 2:
        raise ValueError('Need at least two interfaces (surface and bottom).')
    z = np.empty_like(z_tilde_interfaces)
    z[-1] = -bottom_depth
    for i in range(n_interfaces - 1, 0, -1):
        a = z_tilde_interfaces[i - 1]  # shallower
        b = z_tilde_interfaces[i]  # deeper
        if a == b:
            z[i - 1] = z[i]
            continue
        if method == 'adaptive':
            inc = _adaptive_simpson(
                integrand, a, b, rel_tol, abs_tol, max_recurs_depth
            )
        else:
            nsub = subdivisions
            if method == 'simpson' and nsub % 2 == 1:
                nsub += 1
            inc = _fixed_quadrature(integrand, a, b, nsub, method)
        z[i - 1] = z[i] - inc

    spec_vol, ct, sa = spec_vol_ct_sa_at(z_tilde_interfaces)
    return z, spec_vol, ct, sa


# ---------------------------------------------------------------------------
# Helper functions (non-public)
# ---------------------------------------------------------------------------


def _fixed_quadrature(
    integrand: Callable[[np.ndarray], np.ndarray],
    a: float,
    b: float,
    nsub: int,
    method: str,
) -> float:
    """Composite fixed-step quadrature over [a,b]."""
    h = (b - a) / nsub
    total = 0.0
    if method == 'midpoint':
        mids = a + (np.arange(nsub) + 0.5) * h
        total = np.sum(integrand(mids)) * h
    elif method == 'trapezoid':
        x = a + np.arange(nsub + 1) * h
        fx = integrand(x)
        total = h * (0.5 * fx[0] + fx[1:-1].sum() + 0.5 * fx[-1])
    elif method == 'simpson':
        if nsub % 2 != 0:
            raise ValueError('Simpson requires even nsub.')
        x = a + np.arange(nsub + 1) * h
        fx = integrand(x)
        total = (
            h
            / 3.0
            * (
                fx[0]
                + fx[-1]
                + 4.0 * fx[1:-1:2].sum()
                + 2.0 * fx[2:-2:2].sum()
            )
        )
    elif method in {'gauss2', 'gauss4'}:
        total = _gauss_composite(integrand, a, b, nsub, method)
    else:  # pragma: no cover - defensive
        raise ValueError(f'Unknown quadrature method: {method}')
    return float(total)


def _gauss_composite(
    integrand: Callable[[np.ndarray], np.ndarray],
    a: float,
    b: float,
    nsub: int,
    method: str,
) -> float:
    """Composite Gauss-Legendre quadrature (2- or 4-point)."""
    h = (b - a) / nsub
    total = 0.0
    if method == 'gauss2':
        xi = np.array([-1.0 / np.sqrt(3.0), 1.0 / np.sqrt(3.0)])
        wi = np.array([1.0, 1.0])
    else:  # gauss4
        xi = np.array(
            [
                -0.8611363115940526,
                -0.3399810435848563,
                0.3399810435848563,
                0.8611363115940526,
            ]
        )
        wi = np.array(
            [
                0.34785484513745385,
                0.6521451548625461,
                0.6521451548625461,
                0.34785484513745385,
            ]
        )
    for k in range(nsub):
        a_k = a + k * h
        b_k = a_k + h
        mid = 0.5 * (a_k + b_k)
        half = 0.5 * h
        xk = mid + half * xi
        fx = integrand(xk)
        total += half * np.sum(wi * fx)
    return float(total)


def _adaptive_simpson(
    integrand: Callable[[np.ndarray], np.ndarray],
    a: float,
    b: float,
    rel_tol: float,
    abs_tol: float,
    max_depth: int,
) -> float:
    """Adaptive Simpson integration over [a,b]."""
    fa = integrand(np.array([a]))[0]
    fb = integrand(np.array([b]))[0]
    m = 0.5 * (a + b)
    fm = integrand(np.array([m]))[0]
    whole = _simpson_basic(fa, fm, fb, a, b)
    return _adaptive_simpson_recursive(
        integrand, a, b, fa, fm, fb, whole, rel_tol, abs_tol, max_depth, 0
    )


def _simpson_basic(
    fa: float, fm: float, fb: float, a: float, b: float
) -> float:
    """Single Simpson panel."""
    return (b - a) / 6.0 * (fa + 4.0 * fm + fb)


def _adaptive_simpson_recursive(
    integrand: Callable[[np.ndarray], np.ndarray],
    a: float,
    b: float,
    fa: float,
    fm: float,
    fb: float,
    whole: float,
    rel_tol: float,
    abs_tol: float,
    max_depth: int,
    depth: int,
) -> float:
    m = 0.5 * (a + b)
    lm = 0.5 * (a + m)
    rm = 0.5 * (m + b)
    flm = integrand(np.array([lm]))[0]
    frm = integrand(np.array([rm]))[0]
    left = _simpson_basic(fa, flm, fm, a, m)
    right = _simpson_basic(fm, frm, fb, m, b)
    S2 = left + right
    err = S2 - whole
    tol = max(abs_tol, rel_tol * max(abs(S2), 1e-15))
    if depth >= max_depth:
        return S2
    if abs(err) < 15.0 * tol:
        return S2 + err / 15.0  # Richardson extrapolation
    return _adaptive_simpson_recursive(
        integrand,
        a,
        m,
        fa,
        flm,
        fm,
        left,
        rel_tol,
        abs_tol,
        max_depth,
        depth + 1,
    ) + _adaptive_simpson_recursive(
        integrand,
        m,
        b,
        fm,
        frm,
        fb,
        right,
        rel_tol,
        abs_tol,
        max_depth,
        depth + 1,
    )
