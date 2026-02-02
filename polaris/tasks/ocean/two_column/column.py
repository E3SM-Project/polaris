from typing import Callable

import numpy as np
from scipy.interpolate import PchipInterpolator

from polaris.config import PolarisConfigParser


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
        "{name}_grad" in the "two_column" section.
    x : np.ndarray
        The x-coordinates at which to evaluate the array
    name : str
        The base name of the configuration options

    Returns
    -------
    array : np.ndarray
        The array evaluated at the given x-coordinates
    """
    section = config['two_column']
    mid = section.getnumpy(f'{name}_mid')
    grad = section.getnumpy(f'{name}_grad')

    assert mid is not None, (
        f'The "{name}_mid" configuration option must be set in the '
        '"two_column" section.'
    )
    assert grad is not None, (
        f'The "{name}_grad" configuration option must be set in the '
        '"two_column" section.'
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
    is_increasing = np.all(dz > 0.0)
    is_decreasing = np.all(dz < 0.0)
    if not (is_increasing or is_decreasing):
        raise ValueError(
            'z_tilde_nodes must be strictly monotonic (increasing or '
            'decreasing).'
        )

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
