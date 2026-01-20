import gsw
import xarray as xr


def compute_specvol(
    sa: xr.DataArray, ct: xr.DataArray, p: xr.DataArray
) -> xr.DataArray:
    """
    Compute specific volume from co-located p, CT and SA.

    Notes
    -----
    - This function converts inputs to NumPy arrays and calls
        ``gsw.specvol`` directly for performance. Inputs must fit in
        memory.

    - Any parallelization should be handled by the caller (e.g., splitting
        over outer dimensions and calling this function per chunk).

    Parameters
    ----------
    sa : xarray.DataArray
        Absolute Salinity at the same points as p and ct.

    ct : xarray.DataArray
        Conservative Temperature at the same points as p and sa.

    p : xarray.DataArray
        Sea pressure in Pascals (Pa) at the same points as ct and sa.

    Returns
    -------
    xarray.DataArray
        Specific volume with the same dims/coords as ct and sa (m^3/kg).
    """

    # Check sizes/dims match exactly
    if not (p.sizes == ct.sizes == sa.sizes):
        raise ValueError(
            'p, ct and sa must have identical dimensions and sizes; '
            f'got p={p.sizes}, ct={ct.sizes}, sa={sa.sizes}'
        )

    # Ensure coordinates align identically (names and labels)
    p, ct, sa = xr.align(p, ct, sa, join='exact')

    # Convert to NumPy and call gsw directly for performance
    p_dbar = (p / 1.0e4).to_numpy()
    ct_np = ct.to_numpy()
    sa_np = sa.to_numpy()
    specvol_np = gsw.specvol(sa_np, ct_np, p_dbar)

    specvol = xr.DataArray(
        specvol_np, dims=ct.dims, coords=ct.coords, name='specvol'
    )

    return specvol
