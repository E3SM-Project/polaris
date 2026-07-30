"""
The two-column edge operator for the ``horiz_press_grad`` configurations.

The mesh has exactly two cells and one internal edge, and the edge normal
points from cell 0 to cell 1, so the TRiSK gradient of the design's
``[edge-grad]`` reduces to ``Delta_e f = f_1 - f_0``, with
``[grad_n f]_e = Delta_e f / d_e``.  That is the convention
``Init._compute_montgomery_and_hpga`` uses.

This is a leaf module with no dependencies inside the package, so that both
:py:mod:`~polaris.tasks.ocean.horiz_press_grad.eos_expansion` and
:py:mod:`~polaris.tasks.ocean.horiz_press_grad.finite_volume` can use it
without importing one another.
"""

import xarray as xr

__all__ = ['edge_delta', 'edge_mean']


def edge_delta(field: xr.DataArray) -> xr.DataArray:
    """
    The two-column edge difference ``Delta_e f = f_1 - f_0``, the numerator of
    the TRiSK gradient operator for the single internal edge.

    Parameters
    ----------
    field : xarray.DataArray
        A field with an ``nCells`` dimension of size 2.

    Returns
    -------
    delta : xarray.DataArray
        The difference, with ``nCells`` contracted away.
    """
    _check_two_columns(field)
    return field.isel(nCells=1) - field.isel(nCells=0)


def edge_mean(field: xr.DataArray) -> xr.DataArray:
    """
    The two-column edge average ``0.5 * (f_0 + f_1)``.

    Parameters
    ----------
    field : xarray.DataArray
        A field with an ``nCells`` dimension of size 2.

    Returns
    -------
    mean : xarray.DataArray
        The average, with ``nCells`` contracted away.
    """
    _check_two_columns(field)
    return 0.5 * (field.isel(nCells=0) + field.isel(nCells=1))


def _check_two_columns(field: xr.DataArray) -> None:
    """
    Verify that ``field`` spans exactly the two columns the edge operator is
    defined for.
    """
    ncells = field.sizes.get('nCells', 0)
    if ncells != 2:
        raise ValueError(
            'The two-column edge operator requires exactly 2 cells, but the '
            f'field has {ncells}.'
        )
