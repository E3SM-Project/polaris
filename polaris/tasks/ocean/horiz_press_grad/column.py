from typing import Callable

import numpy as np
from scipy.interpolate import PchipInterpolator

from polaris.config import PolarisConfigParser

# Abscissa offset of the two-point Gauss-Legendre rule on [-1, 1], which is
# exact through cubics and therefore exact for a PCHIP piece.
_GAUSS_OFFSET = 1.0 / np.sqrt(3.0)


def get_array_from_mid_grad(
    config: PolarisConfigParser, name: str, x: np.ndarray
) -> np.ndarray:
    """
    Get an array at a given set of horizontal points based on values defined
    at the midpoint (x=0) and their constant gradient with respect to x.

    Parameters
    ----------
    config : PolarisConfigParser
        The configuration parser containing the options "{name}_mid" and
        "{name}_grad" in the "horiz_press_grad" section.
    x : np.ndarray
        The x-coordinates at which to evaluate the array
    name : str
        The base name of the configuration options

    Returns
    -------
    array : np.ndarray
        The array evaluated at the given x-coordinates
    """
    section = config['horiz_press_grad']
    mid = section.getnumpy(f'{name}_mid')
    grad = section.getnumpy(f'{name}_grad')

    assert mid is not None, (
        f'The "{name}_mid" configuration option must be set in the '
        '"horiz_press_grad" section.'
    )
    assert grad is not None, (
        f'The "{name}_grad" configuration option must be set in the '
        '"horiz_press_grad" section.'
    )

    if isinstance(mid, (list, tuple, np.ndarray)):
        col_count = len(x)
        node_count = len(mid)

        array = np.zeros((col_count, node_count), dtype=float)

        for i in range(col_count):
            array[i, :] = np.array(mid) + x[i] * np.array(grad)
    elif np.isscalar(mid):
        array = mid + x * grad
    else:
        raise ValueError(
            f'The "{name}_mid" configuration option must be a scalar or a '
            'list, tuple or numpy.ndarray.'
        )

    return array


def get_pchip_layer_mean(
    z_tilde_nodes: np.ndarray,
    values_nodes: np.ndarray,
    name: str,
) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    """
    Create a function giving the exact layer mean of a monotone PCHIP profile
    over a layer's pseudo-height range.

    Omega's prognostic conservative temperature and absolute salinity are layer
    *means*, and the higher-order pressure gradient reconstructs them as
    mean-preserving polynomials in pressure, so the initial condition must
    supply layer means rather than samples at layer midpoints.  Within a column
    pressure is exactly linear in pseudo-height, so a mean over a layer's
    pseudo-height range is also its mean over the layer's pressure range and
    there is no ambiguity about which variable to average in.

    The mean is computed by two-point Gauss-Legendre quadrature over each
    profile-node interval the layer overlaps.  PCHIP is piecewise cubic and a
    two-point Gauss rule is exact through cubics, so this is exact rather than
    approximate, and it is preferred over differencing the interpolant's
    antiderivative -- also exact in principle -- because that differences two
    large numbers and so loses precision as the layers thin.  Measured on the
    linear profile of ``hydrostatic_consistency_linear``, the antiderivative
    form departs from the exact layer mean by an amount growing like 1/h
    (7e-14 at 256 m layers, 1.3e-12 at 32 m) while this form sits at 0.9 * eps
    of the salinity itself at every resolution.  That matters because the
    departure limits how exactly the initial condition sits in the scheme's
    exact set, and hence the floor of the machine-precision test.

    Parameters
    ----------
    z_tilde_nodes : np.ndarray
        One-dimensional z-tilde node locations. Must be strictly monotonic
        (increasing or decreasing).
    values_nodes : np.ndarray
        One-dimensional values at ``z_tilde_nodes``.
    name : str
        A descriptive name used in error messages.

    Returns
    -------
    layer_mean : callable
        A function of ``(z_tilde_top, z_tilde_bot)`` -- the pseudo-height of
        each layer's upper and lower interface -- returning the layer means.
        Layers must lie within the node range, but interfaces are allowed to
        fall a round-off distance outside it, which is unavoidable because a
        column's outermost interfaces sit exactly on the outermost nodes in
        several configurations.
    """
    z_tilde_nodes, values_nodes = _check_pchip_nodes(
        z_tilde_nodes, values_nodes, name
    )

    # work in pseudo-depth, which increases downward, so that a layer runs from
    # a smaller to a larger coordinate whichever way the nodes were given
    depth_nodes = -z_tilde_nodes
    order = np.argsort(depth_nodes)
    depth_nodes = depth_nodes[order]

    interpolator = PchipInterpolator(
        depth_nodes, values_nodes[order], extrapolate=False
    )

    depth_min = depth_nodes[0]
    depth_max = depth_nodes[-1]
    # generous against round-off in a column summed over thousands of metres,
    # and tiny against any real configuration error
    depth_tol = 1.0e-9 * (depth_max - depth_min)

    def _layer_mean(
        z_tilde_top: np.ndarray, z_tilde_bot: np.ndarray
    ) -> np.ndarray:
        z_tilde_top = np.asarray(z_tilde_top, dtype=float)
        z_tilde_bot = np.asarray(z_tilde_bot, dtype=float)
        if z_tilde_top.shape != z_tilde_bot.shape:
            raise ValueError(
                'z_tilde_top and z_tilde_bot must have the same shape.'
            )
        if np.any(~np.isfinite(z_tilde_top)) or np.any(
            ~np.isfinite(z_tilde_bot)
        ):
            raise ValueError('Layer interface z_tilde values must be finite.')

        depth_top = -z_tilde_top
        depth_bot = -z_tilde_bot
        if np.any(depth_bot <= depth_top):
            raise ValueError(
                f'Each layer must have positive thickness for {name}: '
                'z_tilde_bot must lie below z_tilde_top.'
            )
        if np.any(depth_top < depth_min - depth_tol) or np.any(
            depth_bot > depth_max + depth_tol
        ):
            raise ValueError(
                f'Layers for {name} must fall within the node range; '
                'extrapolation is not supported.'
            )

        # Absorb the round-off excursion allowed above.  This has to happen
        # before the thickness is taken, so that the interval the quadrature
        # covers and the thickness it is divided by are the same interval; a
        # layer genuinely outside the node range has already been rejected.
        depth_top = np.clip(depth_top, depth_min, depth_max)
        depth_bot = np.clip(depth_bot, depth_min, depth_max)

        # Sum each layer's overlap with each node interval.  Clipping the two
        # interfaces into the interval makes a non-overlapping interval
        # contribute exactly zero width and keeps every quadrature point inside
        # the node range.
        integral = np.zeros(depth_top.shape, dtype=float)
        for interval_top, interval_bot in zip(
            depth_nodes[:-1], depth_nodes[1:], strict=True
        ):
            overlap_top = np.clip(depth_top, interval_top, interval_bot)
            overlap_bot = np.clip(depth_bot, interval_top, interval_bot)
            width = overlap_bot - overlap_top
            middle = 0.5 * (overlap_top + overlap_bot)
            offset = 0.5 * width * _GAUSS_OFFSET
            integral += (
                0.5
                * width
                * (
                    interpolator(middle - offset)
                    + interpolator(middle + offset)
                )
            )

        means = integral / (depth_bot - depth_top)
        if np.any(~np.isfinite(means)):
            raise ValueError(
                f'PCHIP layer averaging produced non-finite values for {name}.'
            )
        return means

    return _layer_mean


def get_pchip_interpolator(
    z_tilde_nodes: np.ndarray,
    values_nodes: np.ndarray,
    name: str,
) -> Callable[[np.ndarray], np.ndarray]:
    """
    Create a monotone PCHIP interpolator for values defined at z-tilde nodes.

    Parameters
    ----------
    z_tilde_nodes : np.ndarray
        One-dimensional z-tilde node locations. Must be strictly monotonic
        (increasing or decreasing).
    values_nodes : np.ndarray
        One-dimensional values at ``z_tilde_nodes``.
    name : str
        A descriptive name used in error messages.

    Returns
    -------
    interpolator : callable
        A function that maps target z-tilde values to interpolated values.
        Targets must lie within the node range; extrapolation is not allowed.
    """
    z_tilde_nodes, values_nodes = _check_pchip_nodes(
        z_tilde_nodes, values_nodes, name
    )

    is_decreasing = z_tilde_nodes[1] < z_tilde_nodes[0]
    if is_decreasing:
        x = -z_tilde_nodes
    else:
        x = z_tilde_nodes

    x_min = x.min()
    x_max = x.max()

    interpolator = PchipInterpolator(x, values_nodes, extrapolate=False)

    def _interp(z_tilde_targets: np.ndarray) -> np.ndarray:
        z_tilde_targets = np.asarray(z_tilde_targets, dtype=float)
        if np.any(~np.isfinite(z_tilde_targets)):
            raise ValueError('Target z_tilde values must be finite.')
        if is_decreasing:
            x_target = -z_tilde_targets
        else:
            x_target = z_tilde_targets
        if np.any(x_target < x_min) or np.any(x_target > x_max):
            raise ValueError(
                f'Target z_tilde values for {name} must fall within the '
                'node range; extrapolation is not supported.'
            )
        values = interpolator(x_target)
        if np.any(~np.isfinite(values)):
            raise ValueError(
                f'PCHIP interpolation produced non-finite values for {name}.'
            )
        return values

    return _interp


def _check_pchip_nodes(
    z_tilde_nodes: np.ndarray,
    values_nodes: np.ndarray,
    name: str,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Validate a set of profile nodes shared by :py:func:`get_pchip_interpolator`
    and :py:func:`get_pchip_layer_mean`, returning them as float arrays.
    """
    z_tilde_nodes = np.asarray(z_tilde_nodes, dtype=float)
    values_nodes = np.asarray(values_nodes, dtype=float)

    if z_tilde_nodes.ndim != 1 or values_nodes.ndim != 1:
        raise ValueError('z_tilde_nodes and values_nodes must be 1-D arrays.')
    if len(z_tilde_nodes) != len(values_nodes):
        raise ValueError(
            f'Lengths of z_tilde_nodes and {name} nodes must match.'
        )
    if len(z_tilde_nodes) < 2:
        raise ValueError('At least two z_tilde nodes are required.')

    dz = np.diff(z_tilde_nodes)
    if not (np.all(dz > 0.0) or np.all(dz < 0.0)):
        raise ValueError(
            'z_tilde_nodes must be strictly monotonic (increasing or '
            'decreasing).'
        )

    return z_tilde_nodes, values_nodes
