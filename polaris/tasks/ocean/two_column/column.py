import numpy as np

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
