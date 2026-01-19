from __future__ import annotations

from typing import Callable, Literal, Sequence

import gsw
import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.two_column.column import get_array_from_mid_grad


class Reference(OceanIOStep):
    """
    A step for creating a high-fidelity reference solution for two column
    test cases

    The reference solution is computed by first converting from the
    Omega pseudo-height coordinate :math:`\tilde z` (``z_tilde``) to true
    geometric height ``z`` by numerically integrating the hydrostatic
    relation

    .. math::

        \frac{\\partial z}{\\partial \tilde z} =
        \rho_0\\,\nu( S_A, \\Theta, p )

    where :math:`\nu` is the specific volume (``spec_vol``) computed from the
    TEOS-10 equation of state, :math:`S_A` is Absolute Salinity,
    :math:`\\Theta` is Conservative Temperature, :math:`p` is sea pressure
    (positive downward), and :math:`\rho_0` is a reference density used in the
    definition of ``z_tilde = - p / (\rho_0 g)`.  The conversion therefore
    requires an integral of the form

    .. math::

        z(\tilde z) = z_b + \\int_{\tilde z_b}^{\tilde z}
        \rho_0\\,\nu\big(S_A(\tilde z'),\\Theta(\tilde z'),p(\tilde z')\big)\\;
        d\tilde z' ,

    with :math:`z_b = -\text{bottom\\_depth}` at the pseudo-height
    ``z_tilde_b`` at the seafloor, typically the minimum (most negative) value
    of the pseudo-height domain for a given water column.

    Then, the horizontal gradient is computed using a 4th-order
    finite-difference stencil at the center column (x=0) to obtain the
    high-fidelity reference solution for the hydrostatic pressure gradient
    error.
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of
        """
        name = 'reference'
        super().__init__(component=component, name=name, indir=indir)
        for file in [
            'reference_solution.nc',
        ]:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        # logger.setLevel(logging.DEBUG)
        config = self.config
        if config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The two_column test case is only supported for the '
                'Omega ocean model.'
            )

        resolution = config.getfloat('two_column', 'reference_resolution')
        assert resolution is not None, (
            'The "reference_resolution" configuration option must be set in '
            'the "two_column" section.'
        )
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )

        x = resolution * np.array([-1.5, -0.5, 0.0, 0.5, 1.5], dtype=float)

        geom_ssh, geom_z_bot = self._get_geom_ssh_z_bot(x)

        vert_levels = config.getint('vertical_grid', 'vert_levels')
        if vert_levels is None:
            raise ValueError(
                'The "vert_levels" configuration option must be set in the '
                '"vertical_grid" section.'
            )

        vert_levs_inters = 2 * vert_levels + 1
        z_tilde = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        z = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        spec_vol = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        ct = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        sa = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)

        z_tilde_node, temperature_node, salinity_node = (
            self._get_z_tilde_t_s_nodes(x)
        )

        for icol in range(len(x)):
            logger.info(f'Computing column {icol}, x = {x[icol]:.3f} km')
            (
                z_tilde[icol, :],
                z[icol, :],
                spec_vol[icol, :],
                ct[icol, :],
                sa[icol, :],
            ) = self._compute_column(
                z_tilde_node=z_tilde_node[icol, :],
                temperature_node=temperature_node[icol, :],
                salinity_node=salinity_node[icol, :],
                geom_ssh=geom_ssh.isel(nCells=icol).item(),
                geom_z_bot=geom_z_bot.isel(nCells=icol).item(),
            )

        # compute montgomery potential M = alpha * p + g * z
        g = constants['SHR_CONST_G']
        montgomery = g * (rho0 * spec_vol * z_tilde + z)

        # the HPGF is grad(M) - p * grad(alpha)
        # Here we just compute the gradient at x=0 using a 4th-order
        # finite-difference stencil
        p0 = rho0 * g * 0.5 * z_tilde[2, :]
        # indices for -1.5dx, -0.5dx, 0.5dx, 1.5dx
        grad_indices = [0, 1, 3, 4]
        dM_dx = _compute_4th_order_gradient(
            montgomery[grad_indices, :], resolution
        )
        dalpha_dx = _compute_4th_order_gradient(
            spec_vol[grad_indices, :], resolution
        )
        hpga = dM_dx - p0 * dalpha_dx

        ds = xr.Dataset()
        ds['temperature'] = xr.DataArray(
            data=ct[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        ds['salinity'] = xr.DataArray(
            data=sa[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'salinity',
                'units': 'g kg-1',
            },
        )

        ds['SpecVol'] = xr.DataArray(
            data=spec_vol[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'specific volume',
                'units': 'm3 kg-1',
            },
        )
        ds['Density'] = 1.0 / ds['SpecVol']
        ds.Density.attrs['long_name'] = 'density'
        ds.Density.attrs['units'] = 'kg m-3'

        ds['ZTildeMid'] = xr.DataArray(
            data=z_tilde[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        ds.ZTildeMid.attrs['long_name'] = 'pseudo-height at layer midpoints'
        ds.ZTildeMid.attrs['units'] = 'm'

        ds['ZTildeInter'] = xr.DataArray(
            data=z_tilde[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
        )
        ds.ZTildeInter.attrs['long_name'] = 'pseudo-height at layer interfaces'
        ds.ZTildeInter.attrs['units'] = 'm'

        ds['GeomZMid'] = xr.DataArray(
            data=z[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'geometric height at layer midpoints',
                'units': 'm',
            },
        )

        ds['GeomZInter'] = xr.DataArray(
            data=z[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
            attrs={
                'long_name': 'geometric height at layer interfaces',
                'units': 'm',
            },
        )

        ds['MontgomeryMid'] = xr.DataArray(
            data=montgomery[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'Montgomery potential at layer midpoints',
                'units': 'm2 s-2',
            },
        )

        ds['MontgomeryInter'] = xr.DataArray(
            data=montgomery[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
            attrs={
                'long_name': 'Montgomery potential at layer interfaces',
                'units': 'm2 s-2',
            },
        )

        ds['HPGAMid'] = xr.DataArray(
            data=hpga[np.newaxis, 1::2],
            dims=['Time', 'nVertLevels'],
            attrs={
                'long_name': 'along-layer pressure gradient acceleration at '
                'midpoints',
                'units': 'm s-2',
            },
        )

        ds['HPGAInter'] = xr.DataArray(
            data=hpga[np.newaxis, 0::2],
            dims=['Time', 'nVertLevelsP1'],
            attrs={
                'long_name': 'along-layer pressure gradient acceleration at '
                'interfaces',
                'units': 'm s-2',
            },
        )

        self.write_model_dataset(ds, 'reference_solution.nc')

    def _get_geom_ssh_z_bot(
        self, x: np.ndarray
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Get the geometric sea surface height and sea floor height for each
        column from the configuration.
        """
        config = self.config
        geom_ssh = get_array_from_mid_grad(config, 'geom_ssh', x)
        geom_z_bot = get_array_from_mid_grad(config, 'geom_z_bot', x)
        return (
            xr.DataArray(data=geom_ssh, dims=['nCells']),
            xr.DataArray(data=geom_z_bot, dims=['nCells']),
        )

    def _init_z_tilde_interface(
        self, pseudo_bottom_depth: float
    ) -> tuple[np.ndarray, int]:
        """
        Compute z-tilde vertical interfaces.
        """
        section = self.config['vertical_grid']
        vert_levels = section.getint('vert_levels')
        bottom_depth = section.getfloat('bottom_depth')
        z_tilde_interface = np.linspace(
            0.0, -bottom_depth, vert_levels + 1, dtype=float
        )
        z_tilde_interface = np.maximum(z_tilde_interface, -pseudo_bottom_depth)
        dz = z_tilde_interface[0:-1] - z_tilde_interface[1:]
        mask = dz == 0.0
        z_tilde_interface[1:][mask] = np.nan

        # max_layer is the index of the deepest non-nan layer interface
        max_layer = np.where(~mask)[0][-1] + 1
        return z_tilde_interface, max_layer

    def _get_z_tilde_t_s_nodes(
        self, x: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get the z-tilde, temperature and salinity node values from the
        configuration.
        """
        config = self.config
        z_tilde_node = get_array_from_mid_grad(config, 'z_tilde', x)
        t_node = get_array_from_mid_grad(config, 'temperature', x)
        s_node = get_array_from_mid_grad(config, 'salinity', x)

        if (
            z_tilde_node.shape != t_node.shape
            or z_tilde_node.shape != s_node.shape
        ):
            raise ValueError(
                'The number of z_tilde, temperature and salinity '
                'points must be the same in each column.'
            )

        self.logger.debug('z_tilde nodes:')
        self.logger.debug(z_tilde_node)
        self.logger.debug('temperature nodes:')
        self.logger.debug(t_node)
        self.logger.debug('salinity nodes:')
        self.logger.debug(s_node)

        return z_tilde_node, t_node, s_node

    def _compute_column(
        self,
        z_tilde_node: np.ndarray,
        temperature_node: np.ndarray,
        salinity_node: np.ndarray,
        geom_ssh: float,
        geom_z_bot: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        config = self.config
        logger = self.logger
        section = config['two_column']
        method = section.get('reference_quadrature_method')
        assert method is not None, (
            'The "reference_quadrature_method" configuration option must be '
            'set in the "two_column" section.'
        )
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )
        water_col_adjust_iter_count = section.getint(
            'water_col_adjust_iter_count'
        )
        assert water_col_adjust_iter_count is not None, (
            'The "water_col_adjust_iter_count" configuration option must be '
            'set in the "two_column" section.'
        )

        goal_geom_water_column_thickness = geom_ssh - geom_z_bot

        # first guess at the pseudo bottom depth is the geometric
        # water column thickness
        pseudo_bottom_depth = goal_geom_water_column_thickness

        logger.debug(
            f'goal_geom_water_column_thickness = '
            f'{goal_geom_water_column_thickness:.12f}'
        )

        for iter in range(water_col_adjust_iter_count):
            z_tilde_inter, max_layer = self._init_z_tilde_interface(
                pseudo_bottom_depth=pseudo_bottom_depth
            )
            vert_levels = len(z_tilde_inter) - 1

            z_tilde_mid = 0.5 * (z_tilde_inter[0:-1] + z_tilde_inter[1:])

            # z_tilde has both interfaces and midpoints
            z_tilde = np.zeros(2 * vert_levels + 1, dtype=float)
            z_tilde[0::2] = z_tilde_inter
            z_tilde[1::2] = z_tilde_mid

            valid = slice(0, 2 * max_layer + 1)

            z_tilde_valid = z_tilde[valid]
            logger.debug(f'z_tilde_valid = {z_tilde_valid}')
            logger.debug(f'z_tilde invalid = {z_tilde[2 * max_layer + 1 :]}')

            z = np.nan * np.ones_like(z_tilde)
            spec_vol = np.nan * np.ones_like(z_tilde)
            ct = np.nan * np.ones_like(z_tilde)
            sa = np.nan * np.ones_like(z_tilde)

            (
                z[valid],
                spec_vol[valid],
                ct[valid],
                sa[valid],
            ) = _integrate_geometric_height(
                z_tilde_interfaces=z_tilde_valid,
                z_tilde_nodes=z_tilde_node,
                sa_nodes=salinity_node,
                ct_nodes=temperature_node,
                bottom_depth=-geom_z_bot,
                rho0=rho0,
                method=method,
            )

            geom_water_column_thickness = z[0] - z[2 * max_layer]

            scaling_factor = (
                goal_geom_water_column_thickness / geom_water_column_thickness
            )
            logger.info(
                f'   Iteration {iter}: '
                f'scaling factor = {scaling_factor:.12f}, '
                f'scaling factor - 1 = {scaling_factor - 1.0:.12g}, '
                f'pseudo bottom depth = {pseudo_bottom_depth:.12f}, '
                f'max layer = {max_layer}'
            )
            pseudo_bottom_depth *= scaling_factor
        logger.info('')

        return z_tilde, z, spec_vol, ct, sa


def _integrate_geometric_height(
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
    if not np.all(np.diff(z_tilde_nodes) <= 0):
        raise ValueError('z_tilde_nodes must be strictly non-increasing.')
    if not np.all(np.diff(z_tilde_interfaces) <= 0):
        raise ValueError('z_tilde_interfaces must be non-increasing.')
    if subdivisions < 1:
        raise ValueError('subdivisions must be >= 1.')

    g = constants['SHR_CONST_G']

    def spec_vol_ct_sa_at(
        z_tilde: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # np.interp requires xp to be increasing; our
        # z_tilde_nodes are decreasing, so flip the signs of
        # z_tilde and z_tilde_nodes for the interpolation
        sa = np.interp(-z_tilde, -z_tilde_nodes, sa_nodes)
        ct = np.interp(-z_tilde, -z_tilde_nodes, ct_nodes)
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


def _compute_4th_order_gradient(f: np.ndarray, dx: float) -> np.ndarray:
    """
    Compute a 4th-order finite-difference gradient of f with respect to x
    at x=0, assuming values at x = dx * [-1.5, -0.5, 0.5, 1.5].

    The stencil is:
        f'(0) ≈ [-f(1.5dx) + 9 f(0.5dx) - 9 f(-0.5dx) + f(-1.5dx)] / (8 dx)

    Here we assume f[0,:], f[1,:], f[2,:], f[3,:] correspond to
    x = -1.5dx, -0.5dx, 0.5dx, 1.5dx respectively.
    """
    assert f.shape[0] == 4, (
        'Input array must have exactly 4 entries in its first dimension '
        'for the 4th-order gradient.'
    )

    # gradient at x = 0 using the non-uniform 4-point stencil
    df_dx = (-f[3, :] + 9.0 * f[2, :] - 9.0 * f[1, :] + f[0, :]) / (8.0 * dx)

    return df_dx
