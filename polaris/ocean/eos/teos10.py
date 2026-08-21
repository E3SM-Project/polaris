from collections.abc import Sequence

import gsw
import numpy as np
import xarray as xr

#: The tracer conventions that :py:func:`convert_tracers()` understands
TRACER_CONVENTIONS = ('teos-10', 'mpas-ocean')

#: The ``long_name`` and ``units`` attributes of the tracers in each
#: convention
TRACER_ATTRS = {
    'teos-10': {
        'temperature': {
            'long_name': 'conservative temperature',
            'units': 'degC',
        },
        'salinity': {
            'long_name': 'absolute salinity',
            'units': 'g kg-1',
        },
    },
    'mpas-ocean': {
        'temperature': {
            'long_name': 'potential temperature',
            'units': 'degC',
        },
        'salinity': {
            'long_name': 'practical salinity',
            'units': 'PSU',
        },
    },
}


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


def ct_from_potential_density(
    sigma_0: xr.DataArray | float,
    sa: xr.DataArray | float,
) -> xr.DataArray | float:
    """
    Compute the conservative temperature that gives a target potential
    density referenced to the surface.

    This is the TEOS-10 counterpart of back-solving a linear equation of
    state for temperature: it lets a test case specify its stratification as
    a density profile rather than a temperature profile.  Because the
    reference pressure is zero, the inversion is exact and needs no
    iteration on pressure.

    Only the cold branch of ``gsw.CT_from_rho`` is physical for seawater
    above its density maximum, which is where all oceanographically relevant
    states lie, so the second root is not returned.

    Parameters
    ----------
    sigma_0 : float or xarray.DataArray
        The target potential density referenced to the surface (kg m-3).
        Note that this is the full density, not the ``sigma`` anomaly, so
        values are near 1027 rather than near 27.

    sa : float or xarray.DataArray
        Absolute Salinity (g kg-1) at the same points as ``sigma_0``.

    Returns
    -------
    float or xarray.DataArray
        Conservative Temperature (degC), with the dims and coords of
        ``sigma_0`` if it is a ``DataArray``.

    Raises
    ------
    ValueError
        If any target density is unattainable at the given salinity, which
        ``gsw`` reports as a NaN root.  Letting that NaN through would
        otherwise propagate silently into an initial condition.
    """
    sigma_0_np = _to_numpy(sigma_0)
    sa_np = _to_numpy(sa)

    ct_np, _ = gsw.CT_from_rho(sigma_0_np, sa_np, 0.0)

    invalid = np.isnan(ct_np) & np.isfinite(sigma_0_np)
    if np.any(invalid):
        bad = np.asarray(sigma_0_np)[invalid]
        raise ValueError(
            f'{invalid.sum()} of the target potential densities are not '
            'attainable at the given absolute salinity; they range from '
            f'{bad.min()} to {bad.max()} kg m-3.'
        )

    if not isinstance(sigma_0, xr.DataArray):
        return float(ct_np)

    ct = xr.DataArray(
        ct_np,
        dims=sigma_0.dims,
        coords=sigma_0.coords,
        name='ct',
    )
    ct.attrs['long_name'] = 'conservative temperature'
    ct.attrs['units'] = 'degC'
    return ct


def convert_tracers(
    ds: xr.Dataset,
    source: str,
    target: str,
    pressure: xr.DataArray | float,
    lon: xr.DataArray | np.ndarray | float,
    lat: xr.DataArray | np.ndarray | float,
    tracer_pairs: Sequence[tuple[str, str]] = (('temperature', 'salinity'),),
) -> xr.Dataset:
    """
    Convert temperature and salinity pairs in ``ds`` between the TEOS-10
    convention (conservative temperature and absolute salinity) and the
    MPAS-Ocean convention (potential temperature and practical salinity)
    using GSW.

    The conversion is performed on a copy; ``ds`` is not modified.  Cells
    where either tracer is NaN (e.g. below the bathymetry) stay NaN.

    Notes
    -----
    ``gsw.pt_from_CT()`` and ``gsw.CT_from_pt()`` take no pressure at all,
    so ``pressure`` enters only through ``gsw.SP_from_SA()`` and
    ``gsw.SA_from_SP()``, whose sensitivity to pressure is far smaller than
    the absolute-salinity correction itself.  An approximate pressure is
    therefore entirely adequate.  In particular, when converting from the
    MPAS-Ocean convention to TEOS-10, a pressure computed from the (not yet
    converted) tracers is accurate enough.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing each of the temperature and salinity variables
        named in ``tracer_pairs``.

    source : {'teos-10', 'mpas-ocean'}
        The tracer convention of the temperature and salinity in ``ds``.

    target : {'teos-10', 'mpas-ocean'}
        The tracer convention to convert to.

    pressure : float or xarray.DataArray
        Sea (gauge) pressure in Pa, broadcastable against the tracers.

    lon : float, numpy.ndarray or xarray.DataArray
        Longitude(s) in degrees, either a nominal scalar value (e.g. on a
        planar mesh) or an array with dimension ``nCells``.

    lat : float, numpy.ndarray or xarray.DataArray
        Latitude(s) in degrees, a scalar or an array with dimension
        ``nCells``, as for ``lon``.

    tracer_pairs : sequence of tuple of str, optional
        The (temperature, salinity) variable-name pairs to convert.

    Returns
    -------
    xarray.Dataset
        A new dataset with the given tracer pairs in the ``target``
        convention.
    """
    for convention in (source, target):
        if convention not in TRACER_CONVENTIONS:
            raise ValueError(
                f'Unknown tracer convention {convention!r}; expected one of '
                + ', '.join(repr(name) for name in TRACER_CONVENTIONS)
            )

    if source == target:
        return ds

    ds_out = ds.copy()
    for temperature_name, salinity_name in tracer_pairs:
        for name in (temperature_name, salinity_name):
            if name not in ds:
                raise ValueError(
                    f"convert_tracers() requires '{name}', which is missing "
                    'from the dataset'
                )
        temperature, salinity = convert_tracer_pair(
            temperature=ds[temperature_name],
            salinity=ds[salinity_name],
            target=target,
            pressure=pressure,
            lon=lon,
            lat=lat,
        )
        ds_out[temperature_name] = temperature
        ds_out[salinity_name] = salinity

    return ds_out


def convert_tracer_pair(
    temperature: xr.DataArray | np.ndarray | float,
    salinity: xr.DataArray | np.ndarray | float,
    target: str,
    pressure: xr.DataArray | float,
    lon: xr.DataArray | np.ndarray | float,
    lat: xr.DataArray | np.ndarray | float,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Convert a single temperature and salinity pair to the ``target``
    convention.

    This is the array-level counterpart of :py:func:`convert_tracers()`, for
    callers that have tracers in hand rather than in a dataset.  See that
    function for the accuracy of ``pressure``.

    Parameters
    ----------
    temperature : float, numpy.ndarray or xarray.DataArray
        Conservative or potential temperature, according to the convention
        being converted from.

    salinity : float, numpy.ndarray or xarray.DataArray
        Absolute or practical salinity, at the same points as
        ``temperature``.

    target : {'teos-10', 'mpas-ocean'}
        The tracer convention to convert to.

    pressure : float or xarray.DataArray
        Sea (gauge) pressure in Pa, broadcastable against the tracers.

    lon : float, numpy.ndarray or xarray.DataArray
        Longitude(s) in degrees, either a nominal scalar value (e.g. on a
        planar mesh) or an array with dimension ``nCells``.

    lat : float, numpy.ndarray or xarray.DataArray
        Latitude(s) in degrees, a scalar or an array with dimension
        ``nCells``, as for ``lon``.

    Returns
    -------
    temperature : xarray.DataArray
        The temperature in the ``target`` convention.

    salinity : xarray.DataArray
        The salinity in the ``target`` convention.
    """
    if target not in TRACER_CONVENTIONS:
        raise ValueError(
            f'Unknown tracer convention {target!r}; expected one of '
            + ', '.join(repr(name) for name in TRACER_CONVENTIONS)
        )

    temperature = _as_data_array(temperature)
    salinity = _as_data_array(salinity)

    temperature_b, salinity_b, pressure_b, lon_b, lat_b = xr.broadcast(
        temperature,
        salinity,
        _as_data_array(pressure),
        _as_data_array(lon),
        _as_data_array(lat),
    )

    temp_in = temperature_b.to_numpy()
    salin_in = salinity_b.to_numpy()
    # Pa -> dbar  (1 dbar = 1e4 Pa)
    p_dbar = pressure_b.to_numpy() / 1.0e4
    lon_np = lon_b.to_numpy()
    lat_np = lat_b.to_numpy()

    valid = np.isfinite(temp_in) & np.isfinite(salin_in)
    temp_out = np.full(temp_in.shape, np.nan)
    salin_out = np.full(salin_in.shape, np.nan)

    if target == 'mpas-ocean':
        # CT, SA -> PT, SP
        temp_out[valid] = gsw.pt_from_CT(salin_in[valid], temp_in[valid])
        salin_out[valid] = gsw.SP_from_SA(
            salin_in[valid], p_dbar[valid], lon_np[valid], lat_np[valid]
        )
    else:
        # PT, SP -> CT, SA
        salin_out[valid] = gsw.SA_from_SP(
            salin_in[valid], p_dbar[valid], lon_np[valid], lat_np[valid]
        )
        temp_out[valid] = gsw.CT_from_pt(salin_out[valid], temp_in[valid])

    temperature_out = _as_converted_data_array(
        data=temp_out,
        template=temperature_b,
        original=temperature,
        attrs=TRACER_ATTRS[target]['temperature'],
    )
    salinity_out = _as_converted_data_array(
        data=salin_out,
        template=salinity_b,
        original=salinity,
        attrs=TRACER_ATTRS[target]['salinity'],
    )

    return temperature_out, salinity_out


def _as_data_array(value: xr.DataArray | np.ndarray | float) -> xr.DataArray:
    """
    Convert ``value`` to a ``DataArray``, treating a 1D array as a field on
    cells.
    """
    if isinstance(value, xr.DataArray):
        return value

    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return xr.DataArray(array)
    if array.ndim == 1:
        return xr.DataArray(array, dims=['nCells'])

    raise ValueError(
        'Only scalars and 1D arrays on cells can be converted to a '
        f'DataArray automatically; got an array with {array.ndim} dimensions'
    )


def _as_converted_data_array(
    data: np.ndarray,
    template: xr.DataArray,
    original: xr.DataArray,
    attrs: dict[str, str],
) -> xr.DataArray:
    """
    Build a converted tracer from ``data``, keeping the dimension order of
    ``original`` where possible and giving it the ``attrs`` of the convention
    it was converted to.

    ``original``'s attributes are dropped rather than merged: they describe
    the tracer before conversion, so anything beyond ``long_name`` and
    ``units`` -- a ``standard_name`` of ``sea_water_conservative_temperature``,
    say -- would be wrong on the way out.
    """
    data_array = xr.DataArray(
        data=data,
        dims=template.dims,
        coords=template.coords,
        attrs=dict(attrs),
    )
    if set(data_array.dims) == set(original.dims):
        data_array = data_array.transpose(*original.dims)
    return data_array


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
