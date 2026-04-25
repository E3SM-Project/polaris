import gsw
import xarray as xr


def compute_specvol(
    sa: xr.DataArray | float,
    ct: xr.DataArray | float,
    p: xr.DataArray | float,
) -> xr.DataArray | float:
    """
    Compute specific volume from co-located p, CT and SA.

    Notes
    -----
    - For xarray inputs, this function converts inputs to NumPy arrays
        and calls ``gsw.specvol`` directly for performance. Inputs must
        fit in memory.

    - Any parallelization should be handled by the caller (e.g., splitting
        over outer dimensions and calling this function per chunk).

    Parameters
    ----------
    sa : float or xarray.DataArray
        Absolute Salinity at the same points as p and ct.

    ct : float or xarray.DataArray
        Conservative Temperature at the same points as p and sa.

    p : float or xarray.DataArray
        Sea pressure in Pascals (Pa) at the same points as ct and sa.

    Returns
    -------
    float or xarray.DataArray
        Specific volume with the same dims/coords as the input arrays
        (m^3/kg), or a scalar if all inputs are scalar.
    """

    if not any(isinstance(value, xr.DataArray) for value in (p, ct, sa)):
        p_dbar = p / 1.0e4
        specvol = gsw.specvol(sa, ct, p_dbar)
        return float(specvol)

    p, ct, sa = _align_data_arrays(p=p, ct=ct, sa=sa)
    template = _get_template_data_array(p=p, ct=ct, sa=sa)

    # Convert to NumPy and call gsw directly for performance
    p_dbar = _to_numpy(p) / 1.0e4
    ct_np = _to_numpy(ct)
    sa_np = _to_numpy(sa)
    specvol_np = gsw.specvol(sa_np, ct_np, p_dbar)

    specvol = xr.DataArray(
        specvol_np,
        dims=template.dims,
        coords=template.coords,
        name='specvol',
    )

    return specvol


def _align_data_arrays(
    p: xr.DataArray | float,
    ct: xr.DataArray | float,
    sa: xr.DataArray | float,
) -> tuple[xr.DataArray | float, xr.DataArray | float, xr.DataArray | float]:
    data_arrays = [
        value for value in (p, ct, sa) if isinstance(value, xr.DataArray)
    ]

    if len(data_arrays) <= 1:
        return p, ct, sa

    dims = [data_array.dims for data_array in data_arrays]
    sizes = [data_array.sizes for data_array in data_arrays]
    if any(dim != dims[0] for dim in dims) or any(
        size != sizes[0] for size in sizes
    ):
        raise ValueError(
            'DataArray inputs must have identical dimensions and sizes; '
            f'got p={_sizes_str(p)}, ct={_sizes_str(ct)}, sa={_sizes_str(sa)}'
        )

    aligned = iter(xr.align(*data_arrays, join='exact'))
    if isinstance(p, xr.DataArray):
        p = next(aligned)
    if isinstance(ct, xr.DataArray):
        ct = next(aligned)
    if isinstance(sa, xr.DataArray):
        sa = next(aligned)

    return p, ct, sa


def _get_template_data_array(
    p: xr.DataArray | float,
    ct: xr.DataArray | float,
    sa: xr.DataArray | float,
) -> xr.DataArray:
    for value in (ct, sa, p):
        if isinstance(value, xr.DataArray):
            return value

    raise ValueError('At least one input must be an xarray.DataArray.')


def _to_numpy(value: xr.DataArray | float):
    if isinstance(value, xr.DataArray):
        return value.to_numpy()

    return value


def _sizes_str(value: xr.DataArray | float) -> str:
    if isinstance(value, xr.DataArray):
        return str(value.sizes)

    return 'scalar'
