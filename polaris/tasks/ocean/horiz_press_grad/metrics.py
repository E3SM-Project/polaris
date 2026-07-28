"""
Shared error metrics and small formatting helpers for the two-column
``horiz_press_grad`` analysis steps.

This module is deliberately dependency-light (numpy and xarray only) so that
both the reference-based :py:class:`~polaris.tasks.ocean.horiz_press_grad.
analysis.Analysis` step and the reference-free
:py:class:`~polaris.tasks.ocean.horiz_press_grad.resting_analysis.
RestingAnalysis` step can use it without importing one another.
"""

import numpy as np
import xarray as xr

__all__ = [
    'get_internal_edge',
    'rms',
    'power_law_fit',
    'write_metric_dataset',
    'format_value_list',
    'format_value_error_pairs',
]


def get_internal_edge(ds_mesh: xr.Dataset) -> tuple[int, tuple[int, int]]:
    """
    Determine the edge that connects the two valid cells in the two-column
    mesh.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The culled horizontal mesh, which must contain ``cellsOnEdge``.

    Returns
    -------
    edge_index : int
        The zero-based index of the single internal edge.

    cells_on_edge : tuple of int
        The zero-based indices of the two cells bounding that edge.
    """
    if 'cellsOnEdge' not in ds_mesh:
        raise ValueError('cellsOnEdge is required in culled_mesh.nc')

    cells_on_edge = ds_mesh.cellsOnEdge.values.astype(int)
    if cells_on_edge.ndim != 2 or cells_on_edge.shape[1] != 2:
        raise ValueError('cellsOnEdge must have shape (nEdges, 2).')

    valid = np.logical_and(cells_on_edge[:, 0] > 0, cells_on_edge[:, 1] > 0)
    valid_edges = np.where(valid)[0]
    if len(valid_edges) != 1:
        raise ValueError(
            'Expected exactly one edge with two valid cells in the '
            f'two-column mesh, found {len(valid_edges)}.'
        )

    edge_index = int(valid_edges[0])
    # convert from 1-based MPAS indexing to 0-based indexing
    cell0 = int(cells_on_edge[edge_index, 0] - 1)
    cell1 = int(cells_on_edge[edge_index, 1] - 1)
    return edge_index, (cell0, cell1)


def rms(values: np.ndarray) -> float:
    """
    Compute the root mean square over finite values.

    Parameters
    ----------
    values : numpy.ndarray
        The values to reduce.  Non-finite entries are ignored.

    Returns
    -------
    float
        The RMS of the finite entries.
    """
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    if not np.any(valid):
        raise ValueError('No finite values available for RMS error.')
    return float(np.sqrt(np.mean(values[valid] ** 2)))


def power_law_fit(
    x: np.ndarray,
    y: np.ndarray,
    fit_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, float, float]:
    """
    Fit ``y = 10**b * x**m`` in log10 space.

    Parameters
    ----------
    x : numpy.ndarray
        The abscissa (resolution or tilt).  Only positive, finite entries
        take part in the fit.

    y : numpy.ndarray
        The ordinate (an error metric).  Only positive, finite entries take
        part in the fit.

    fit_mask : numpy.ndarray, optional
        An additional boolean mask restricting which points are fit.

    Returns
    -------
    fit : numpy.ndarray
        The fitted curve evaluated at every entry of ``x``.

    slope : float
        The fitted exponent ``m``.

    intercept : float
        The fitted ``log10`` intercept ``b``.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.logical_and.reduce(
        (np.isfinite(x), np.isfinite(y), x > 0.0, y > 0.0)
    )
    if fit_mask is not None:
        fit_mask = np.asarray(fit_mask, dtype=bool)
        if fit_mask.shape != x.shape:
            raise ValueError(
                'fit_mask must have the same shape as x and y for '
                'power-law fitting.'
            )
        valid = np.logical_and(valid, fit_mask)

    if np.count_nonzero(valid) < 2:
        raise ValueError(
            'At least two positive finite points are required for fit.'
        )

    poly = np.polyfit(np.log10(x[valid]), np.log10(y[valid]), 1)
    slope = float(poly[0])
    intercept = float(poly[1])
    fit = x**slope * 10.0**intercept
    return fit, slope, intercept


def write_metric_dataset(
    filename: str,
    resolution_km: np.ndarray,
    rms_error: np.ndarray,
    y_name: str,
    y_units: str,
    fit: np.ndarray | None = None,
    slope: float | None = None,
    intercept: float | None = None,
) -> None:
    """
    Write the data used in a convergence plot to netCDF.

    Parameters
    ----------
    filename : str
        The netCDF file to write.

    resolution_km : numpy.ndarray
        The horizontal resolutions in km.

    rms_error : numpy.ndarray
        The error metric at each resolution.

    y_name : str
        The variable name to give ``rms_error``.

    y_units : str
        The units of ``rms_error``.

    fit : numpy.ndarray, optional
        A fitted curve to include.

    slope : float, optional
        The fitted exponent, stored as a global attribute.

    intercept : float, optional
        The fitted ``log10`` intercept, stored as a global attribute.
    """
    nres = len(resolution_km)
    ds = xr.Dataset()
    ds['resolution_km'] = xr.DataArray(
        data=resolution_km,
        dims=['nResolutions'],
        attrs={'long_name': 'horizontal resolution', 'units': 'km'},
    )
    ds[y_name] = xr.DataArray(
        data=rms_error,
        dims=['nResolutions'],
        attrs={'long_name': y_name.replace('_', ' '), 'units': y_units},
    )
    if fit is not None:
        ds['power_law_fit'] = xr.DataArray(
            data=fit,
            dims=['nResolutions'],
            attrs={
                'long_name': 'power-law fit to rms error',
                'units': y_units,
            },
        )
    if slope is not None:
        ds.attrs['fit_slope'] = slope
    if intercept is not None:
        ds.attrs['fit_intercept_log10'] = intercept
    ds.attrs['nResolutions'] = nres
    ds.to_netcdf(filename)


def format_value_list(values: np.ndarray) -> str:
    """
    Format an array as a compact list of floats.

    Parameters
    ----------
    values : numpy.ndarray
        The values to format.

    Returns
    -------
    str
        A bracketed, comma-separated list.
    """
    formatted = [f'{float(value):g}' for value in values]
    return f'[{", ".join(formatted)}]'


def format_value_error_pairs(
    values: np.ndarray,
    errors: np.ndarray,
    units: str = 'km',
) -> str:
    """
    Format value/error pairs as readable key-value text.

    Parameters
    ----------
    values : numpy.ndarray
        The abscissa values.

    errors : numpy.ndarray
        The error metric at each value.

    units : str, optional
        The units to label ``values`` with.

    Returns
    -------
    str
        A semicolon-separated list of ``value units: error`` pairs.
    """
    pairs = [
        f'{float(value):g} {units}: {float(error):.3e}'
        for value, error in zip(values, errors, strict=True)
    ]
    return '; '.join(pairs)
