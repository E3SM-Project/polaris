from __future__ import annotations

from typing import Callable

import gsw
import numpy as np

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.horiz_press_grad.column import (
    get_array_from_mid_grad,
    get_pchip_interpolator,
)


class ReferenceColumn:
    r"""
    Continuous, coordinate-invariant HPGA reference a(z̃) at the edge x=0.

    Evaluates the along-pseudo-height horizontal pressure-gradient
    acceleration (HPGA) via the chain-rule / Leibniz expansion, anchored at
    the surface (the boundary the model honours):

    .. math::

        a(\tilde z) = -g\left[\eta' - \rho_0\,\alpha(\tilde z_s)\,
           \tilde z_s' + \rho_0 \int_{\tilde z_s}^{\tilde z}
           \bigl(\alpha_{S_A}\,\partial_x S_A
           + \alpha_{\Theta}\,\partial_x \Theta\bigr)\,
           d\tilde z'\right]

    where :math:`\eta' = \partial_x \eta` is the sea-surface-height gradient,
    :math:`\tilde z_s` is the surface pseudo-height (zero only when the surface
    pressure is zero) and :math:`\tilde z_s' = \partial_x \tilde z_s` its
    gradient (all in the edge-normal direction), :math:`\alpha` is specific
    volume, and :math:`\alpha_{S_A}`, :math:`\alpha_{\Theta}` are TEOS-10
    specific-volume first derivatives.  The surface boundary term is kept
    general so nonzero sea-surface height and surface pressure are supported.
    The x-gradients of :math:`S_A` and :math:`\Theta` at fixed :math:`\tilde z`
    are obtained by centred PCHIP differencing, which correctly handles
    moving-node inputs (e.g. the ``ztilde_gradient`` task).

    Because the continuous pressure-gradient force is coordinate-invariant,
    this along-pseudo-height formula equals :math:`-g\,\partial z/\partial
    x|_{\tilde z}` exactly, and is valid at any pseudo-height including near
    the seafloor.
    """

    def __init__(
        self,
        config: PolarisConfigParser,
        x_sign: float = 1.0,
    ):
        """
        Parameters
        ----------
        config : PolarisConfigParser
            Configuration containing a ``horiz_press_grad`` section.
        x_sign : float
            +1 or -1, mapping the config +x direction onto the edge normal.
            Derived from ``sign(xCell[cell1] - xCell[cell0])`` in
            ``Analysis``.
        """
        section = config['horiz_press_grad']
        method = section.get('reference_quadrature_method')
        nsub = section.getint('reference_quadrature_subdivisions')
        # Differencing half-width in km. ``get_array_from_mid_grad`` multiplies
        # the per-km config gradients by x, so x must be supplied in km; the
        # resulting centred differences are converted to per-metre below.
        eps_km = section.getfloat('reference_horiz_eps_km')

        self._method = method
        self._nsub = nsub
        # full centred-difference width in metres (2 * eps_km, km -> m)
        self._two_eps_m = 2.0 * eps_km * 1000.0
        self._x_sign = x_sign

        # Surface anchor. The model honours the surface boundary (sea-surface
        # height and surface pressure), so the reference integral is anchored
        # there rather than at the seafloor. These are kept fully general so a
        # follow-up surface-pressure test (nonzero geom_ssh_grad and/or a
        # nonzero top z_tilde node) is supported without further changes.
        geom_ssh_grad = section.getfloat('geom_ssh_grad')
        z_tilde_mid = section.getnumpy('z_tilde_mid')
        z_tilde_grad = section.getnumpy('z_tilde_grad')
        # the surface is the shallowest (largest) pseudo-height node
        surf_node = int(np.argmax(z_tilde_mid))

        self._z_tilde_surf = float(z_tilde_mid[surf_node])
        # Convert config gradients from m/km to m/m; project onto edge normal
        self._eta_prime = (geom_ssh_grad / 1000.0) * x_sign
        self._zt_surf_prime = (z_tilde_grad[surf_node] / 1000.0) * x_sign

        # Evaluate node arrays at x = 0, +eps, -eps in km (config x direction)
        x_eval = np.array([0.0, eps_km, -eps_km])
        z_tilde_nodes = get_array_from_mid_grad(config, 'z_tilde', x_eval)
        ct_nodes = get_array_from_mid_grad(config, 'temperature', x_eval)
        sa_nodes = get_array_from_mid_grad(config, 'salinity', x_eval)

        # Build clamped PCHIP interpolants for SA and CT at each x
        self._sa_0 = _ClampedInterp(z_tilde_nodes[0], sa_nodes[0], 'salinity')
        self._ct_0 = _ClampedInterp(
            z_tilde_nodes[0], ct_nodes[0], 'temperature'
        )
        self._sa_plus = _ClampedInterp(
            z_tilde_nodes[1], sa_nodes[1], 'salinity'
        )
        self._ct_plus = _ClampedInterp(
            z_tilde_nodes[1], ct_nodes[1], 'temperature'
        )
        self._sa_minus = _ClampedInterp(
            z_tilde_nodes[2], sa_nodes[2], 'salinity'
        )
        self._ct_minus = _ClampedInterp(
            z_tilde_nodes[2], ct_nodes[2], 'temperature'
        )

    def specvol(self, z_tilde: np.ndarray) -> np.ndarray:
        """Specific volume at x=0 (m³ kg⁻¹)."""
        z_tilde = np.asarray(z_tilde, dtype=float)
        sa = self._sa_0(z_tilde)
        ct = self._ct_0(z_tilde)
        p_pa = -RhoSw * Gravity * z_tilde
        return gsw.specvol(sa, ct, p_pa * 1.0e-4)

    def dalpha_dx(self, z_tilde: np.ndarray) -> np.ndarray:
        """d(α)/d(edge-normal) at fixed z̃ (m² kg⁻¹ m⁻¹)."""
        z_tilde = np.asarray(z_tilde, dtype=float)
        p_pa = -RhoSw * Gravity * z_tilde
        v_sa, v_ct, _ = gsw.specvol_first_derivatives(
            self._sa_0(z_tilde), self._ct_0(z_tilde), p_pa * 1.0e-4
        )
        # nodes were evaluated at x = +/- eps_km (km); dividing by the width in
        # metres yields dSA/dx and dCT/dx in (g/kg)/m and degC/m.
        two_eps = self._two_eps_m
        dsa = (self._sa_plus(z_tilde) - self._sa_minus(z_tilde)) / two_eps
        dct = (self._ct_plus(z_tilde) - self._ct_minus(z_tilde)) / two_eps
        # x_sign projects the config-x gradient onto the edge-normal direction
        return (v_sa * dsa + v_ct * dct) * self._x_sign

    def hpga(self, z_tilde: np.ndarray) -> np.ndarray:
        """Reference HPGA in the edge-normal direction (m s⁻²)."""
        z_tilde = np.asarray(z_tilde, dtype=float)
        flat = z_tilde.ravel()
        z_surf = self._z_tilde_surf

        # Clamp targets to the surface; targets above it are unphysical
        flat = np.minimum(flat, z_surf)

        # Sorted unique set containing the surface and all (clamped) targets
        unique_z = np.unique(np.concatenate([[z_surf], flat]))

        # Cumulative integral, then re-reference to the surface so that
        # I(z̃) = ∫_{z̃_surf}^{z̃} dalpha_dx dz̃' (zero at the surface).
        I_cum = np.zeros(len(unique_z))
        for i in range(1, len(unique_z)):
            I_cum[i] = I_cum[i - 1] + _fixed_quadrature(
                self.dalpha_dx,
                unique_z[i - 1],
                unique_z[i],
                self._nsub,
                self._method,
            )
        I_cum -= np.interp(z_surf, unique_z, I_cum)

        I_at = np.interp(flat, unique_z, I_cum)
        alpha_surf = float(self.specvol(np.array([z_surf]))[0])
        # Surface boundary term, kept general for nonzero sea-surface height
        # and surface pressure (eta' and the surface pseudo-height gradient).
        C = self._eta_prime - RhoSw * alpha_surf * self._zt_surf_prime
        return (-Gravity * (C + RhoSw * I_at)).reshape(z_tilde.shape)

    def layer_mean_hpga(self, z_tilde_interfaces: np.ndarray) -> np.ndarray:
        """
        Layer-averaged HPGA in the edge-normal direction (m s⁻²).

        Parameters
        ----------
        z_tilde_interfaces : ndarray
            Shape ``(nLayers+1,)`` interface pseudo-heights, decreasing
            from surface (index 0) to seafloor (index -1).

        Returns
        -------
        ndarray
            Shape ``(nLayers,)`` Gauss-weighted layer-mean HPGA.
        """
        z_tilde_interfaces = np.asarray(z_tilde_interfaces, dtype=float)
        n_layers = len(z_tilde_interfaces) - 1

        # 4-point Gauss–Legendre nodes and weights on [-1, 1]
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

        all_pts: list[float] = []
        all_wts: list[float] = []
        slices: list[tuple[int, int]] = []
        layer_dz: list[float] = []

        for k in range(n_layers):
            z_top = float(z_tilde_interfaces[k])
            z_bot = float(z_tilde_interfaces[k + 1])
            dz = z_top - z_bot
            layer_dz.append(dz)
            h = dz / self._nsub
            start = len(all_pts)
            for s in range(self._nsub):
                a_s = z_bot + s * h
                b_s = a_s + h
                mid_s = 0.5 * (a_s + b_s)
                half = 0.5 * h
                for j in range(len(xi)):
                    all_pts.append(float(mid_s + half * xi[j]))
                    all_wts.append(float(wi[j] * half))
            slices.append((start, len(all_pts)))

        pts_arr = np.array(all_pts)
        wts_arr = np.array(all_wts)
        a_arr = self.hpga(pts_arr)

        result = np.zeros(n_layers)
        for k in range(n_layers):
            s0, s1 = slices[k]
            if layer_dz[k] > 0.0:
                result[k] = np.dot(wts_arr[s0:s1], a_arr[s0:s1]) / layer_dz[k]
        return result


class _ClampedInterp:
    """PCHIP interpolant clamped (constant-extended) at its node boundaries."""

    def __init__(
        self,
        z_tilde_nodes: np.ndarray,
        values_nodes: np.ndarray,
        name: str,
    ):
        self._interp = get_pchip_interpolator(
            z_tilde_nodes, values_nodes, name
        )
        self._z_min = float(np.min(z_tilde_nodes))
        self._z_max = float(np.max(z_tilde_nodes))

    def __call__(self, z_tilde: np.ndarray) -> np.ndarray:
        z = np.clip(np.asarray(z_tilde, dtype=float), self._z_min, self._z_max)
        return self._interp(z)


# ---- quadrature primitives --------------------------------------------------


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
