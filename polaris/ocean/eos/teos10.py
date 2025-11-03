import gsw
import xarray as xr


def compute_specvol(
    SA: xr.DataArray, CT: xr.DataArray, p: xr.DataArray
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
    SA : xarray.DataArray
        Absolute Salinity at the same points as p and CT.

    CT : xarray.DataArray
        Conservative Temperature at the same points as p and SA.

    p : xarray.DataArray
        Sea pressure in Pascals (Pa) at the same points as CT and SA.

    Returns
    -------
    xarray.DataArray
        Specific volume with the same dims/coords as CT and SA (m^3/kg).
    """

    # Check sizes/dims match exactly
    if not (p.sizes == CT.sizes == SA.sizes):
        raise ValueError(
            'p, CT and SA must have identical dimensions and sizes; '
            f'got p={p.sizes}, CT={CT.sizes}, SA={SA.sizes}'
        )

    # Ensure coordinates align identically (names and labels)
    p, CT, SA = xr.align(p, CT, SA, join='exact')

    # Convert to NumPy and call gsw directly for performance
    p_dbar = (p / 1.0e4).to_numpy()
    CT_np = CT.to_numpy()
    SA_np = SA.to_numpy()
    specvol_np = gsw.specvol(SA_np, CT_np, p_dbar)

    specvol = xr.DataArray(
        specvol_np, dims=CT.dims, coords=CT.coords, name='specvol'
    )

    return specvol.assign_attrs(
        {
            'long_name': 'specific volume',
            'units': 'm^3 kg^-1',
            'standard_name': 'specific_volume',
        }
    )
