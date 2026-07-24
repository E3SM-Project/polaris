import gsw
import numpy as np
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


def convert_tracers_to_mpas_ocean(ds, lon, lat):
    """
    Convert conservative temperature and absolute salinity in ``ds`` to the
    MPAS-Ocean tracer conventions (potential temperature and practical
    salinity) using GSW.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset with ``temperature`` (conservative temperature, degC),
        ``salinity`` (absolute salinity, g/kg), and ``pressure`` (Pa),
        each with dimensions ``(Time, nCells, nVertLevels)``.

    lon : float or numpy.ndarray
        Longitude(s) in degrees used in the practical-salinity conversion,
        either a nominal scalar value (e.g. on a planar mesh) or an array
        with dimension ``nCells``.

    lat : float or numpy.ndarray
        Latitude(s) in degrees, a scalar or an array with dimension
        ``nCells``, as for ``lon``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``temperature`` as potential temperature (degC) and
        ``salinity`` as practical salinity (PSU).
    """
    ct = ds['temperature'].values  # (Time, nCells, nVertLevels)
    sa = ds['salinity'].values
    p_pa = ds['pressure'].values  # Pa
    p_dbar = p_pa / 1e4  # Pa -> dbar  (1 dbar = 1e4 Pa)

    lon_arr = np.asarray(lon, dtype=float)
    lat_arr = np.asarray(lat, dtype=float)
    if lon_arr.ndim == 1:
        # (nCells,) -> (Time, nCells, nVertLevels) broadcast shape
        lon_arr = lon_arr[np.newaxis, :, np.newaxis]
        lat_arr = lat_arr[np.newaxis, :, np.newaxis]
    lon_3d = np.broadcast_to(lon_arr, ct.shape)
    lat_3d = np.broadcast_to(lat_arr, ct.shape)

    valid = np.isfinite(ct) & np.isfinite(sa)
    pot_temp = np.full_like(ct, np.nan)
    prac_sal = np.full_like(sa, np.nan)

    pot_temp[valid] = gsw.pt_from_CT(sa[valid], ct[valid])
    prac_sal[valid] = gsw.SP_from_SA(
        sa[valid], p_dbar[valid], lon_3d[valid], lat_3d[valid]
    )

    ds['temperature'] = xr.DataArray(
        data=pot_temp,
        dims=ds['temperature'].dims,
        attrs={
            'long_name': 'potential temperature',
            'units': 'degC',
        },
    )
    ds['salinity'] = xr.DataArray(
        data=prac_sal,
        dims=ds['salinity'].dims,
        attrs={
            'long_name': 'practical salinity',
            'units': 'PSU',
        },
    )
    return ds


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
