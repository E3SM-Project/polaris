import importlib.resources as imp_res

import numpy as np
import xarray as xr
from ruamel.yaml import YAML

from polaris.constants import get_constant
from polaris.ocean.vertical.ztilde import (
    get_iter_count_for_eos,
    pressure_and_spec_vol_from_state_at_geom_height,
    pseudothickness_from_pressure,
)

RhoSw = get_constant('seawater_density_reference')


def _variables_at_layer_tops():
    """
    The MPAS-Ocean variables that ``variables.yaml`` lists as defined at
    the top of each layer but written on ``nVertLevels``
    """
    text = (
        imp_res.files('polaris.ocean.model')
        .joinpath('variables.yaml')
        .read_text()
    )
    nested_dict = YAML(typ='rt').load(text)
    return nested_dict['mpas-ocean']['variables_at_layer_tops']


def geom_thickness_from_ds(ds, config):
    """
    Extract or compute geometric layer thickness from dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        An ocean dataset containing either 'layerThickness' directly, or
        'SpecVol' and 'PseudoThickness' to compute it

    config : polaris.config.PolarisConfigParser
        Configuration options for the test case

    Returns
    -------
    layer_thickness : xarray.DataArray
        The geometric layer thickness in meters

    Raises
    ------
    ValueError
        If neither layerThickness nor the variables needed to compute it
        are present in the dataset
    """
    if 'layerThickness' in ds.keys():
        return ds['layerThickness']
    elif 'SpecVol' in ds.keys() and 'PseudoThickness' in ds.keys():
        return RhoSw * ds['SpecVol'] * ds['PseudoThickness']
    else:
        raise ValueError(
            'Geometric layerThickness is not present in the '
            'initial condition and PseudoThickness and SpecVol are not '
            'present to compute it'
        )


def pseudothickness_from_ds(
    ds,
    config,
    src_var_name='layerThickness',
    iter_count=None,
    surf_pressure=None,
):
    """
    Compute pseudothickness from temperature and salinity in dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        An ocean dataset containing 'temperature', 'salinity' and
        src_var_name, along with 'SurfacePressure' if ``surf_pressure`` is
        not given

    config : polaris.config.PolarisConfigParser
        Configuration options for the test case

    src_var_name : str, optional
        The name of the variable in ds to use as the source for the
        geometric thickness, by default 'layerThickness'.

    iter_count : int, optional
        The number of iterations to use when computing pressure and
        specific volume, by default ``pseudothickness_iter_count`` for teos-10
        and 1 for linear or constant EOS.

    surf_pressure : float or xarray.DataArray, optional
        The surface pressure to integrate down from.  Defaults to
        ``ds.SurfacePressure``.  Pass 0. for quantities that are defined at
        zero surface pressure, such as ``restingThickness``.

    Returns
    -------
    pseudothickness : xarray.DataArray or None
        The pseudothickness computed from pressure, or None if
        temperature and salinity are not available

    spec_vol : xarray.DataArray or None
        The specific volume computed from model state, or None if
        temperature and salinity are not available
    """
    if 'temperature' not in ds.keys() or 'salinity' not in ds.keys():
        print(
            'PseudoThickness is not present in the '
            'initial condition and T,S are not present '
            'to compute it'
        )
        return None, None

    if iter_count is None:
        iter_count = get_iter_count_for_eos(config)

    if surf_pressure is None:
        if 'SurfacePressure' not in ds.keys():
            raise ValueError(
                'pseudothickness_from_ds() requires SurfacePressure in the '
                'dataset or an explicit surf_pressure argument.'
            )
        surf_pressure = ds.SurfacePressure

    src_var = ds[src_var_name]
    src_has_time = 'Time' in src_var.dims
    if not src_has_time:
        src_var = src_var.expand_dims(dim='Time', axis=0)
    p_interface, _, spec_vol = pressure_and_spec_vol_from_state_at_geom_height(
        config,
        src_var,
        ds.temperature,
        ds.salinity,
        surf_pressure,
        iter_count=iter_count,
    )

    pseudothickness = pseudothickness_from_pressure(p_interface)

    if not src_has_time:
        pseudothickness = pseudothickness.squeeze(dim='Time')
        spec_vol = spec_vol.squeeze(dim='Time')

    return pseudothickness, spec_vol


def get_z_mid_and_interface(ds, allow_reconstruct=False):
    """
    Get the elevation of layer midpoints and of layer interfaces

    What the model wrote is preferred.  Reconstructing them from
    ``layerThickness`` is available but off by default, because it is not
    always valid: the monthly mean of geometric thickness cannot be derived
    from the monthly means of pseudo-thickness and specific volume, so
    analysis of monthly means has to read what the model wrote or refuse.

    Parameters
    ----------
    ds : xarray.Dataset
        A data set holding the vertical geometry, with MPAS-Ocean names

    allow_reconstruct : bool, optional
        Whether to reconstruct the geometry from ``layerThickness`` when the
        data set does not carry it

    Returns
    -------
    z_mid : xarray.DataArray
        The elevation of layer midpoints, in m, positive up

    z_interface : xarray.DataArray
        The elevation of layer interfaces, in m, positive up

    Raises
    ------
    ValueError
        If the data set lacks the geometry and it may not be reconstructed
    """
    missing = [name for name in ('zMid', 'GeomZInterface') if name not in ds]
    if not missing:
        return ds.zMid, ds.GeomZInterface
    if not allow_reconstruct:
        raise ValueError(
            f'The data set has no {", ".join(missing)}, which is the '
            f'vertical geometry an elevation is a position in.  Polaris '
            f'cannot reconstruct it from the monthly means of the other '
            f'fields, so a simulation has to write it for its output to be '
            f'analysed at an elevation.'
        )
    return _reconstruct_z_mid_and_interface(ds)


def depth_from_thickness(ds):
    """
    Get the elevation of the midpoint of each layer

    A thin face on :py:func:`get_z_mid_and_interface` for callers that want
    only the midpoints.  What the model wrote is preferred; the geometry is
    reconstructed from ``layerThickness`` when it is absent.

    Parameters
    ----------
    ds : xarray.Dataset
        An ocean dataset carrying the geometry or ``layerThickness``, and
        optionally ``ssh`` and ``bottomDepth``

    Returns
    -------
    z_mid : xarray.DataArray
        The location in meters from the sea surface of the midpoint of each
        layer, positive upward
    """
    z_mid, _ = get_z_mid_and_interface(ds, allow_reconstruct=True)
    return z_mid


_VERT_COORD_VAR_NAMES = {
    'cell-center': 'zMid',
    'cell-interfaces': 'GeomZInterface',
    'cell-top': 'zTop',
}


def vertical_coord_from_location(ds, location, allow_reconstruct=False):
    """
    Get the vertical coordinate field appropriate for a variable at a given
    location in ``ds``

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with no ``Time`` dimension or a ``Time`` dimension of
        length one

    location : {'cell-center', 'cell-interfaces', 'cell-top'}
        Where the variable is defined: layer midpoints, layer interfaces,
        or the top of each layer

    allow_reconstruct : bool, optional
        Whether to reconstruct the coordinate from ``layerThickness`` via
        :py:func:`_reconstruct_z_mid_and_interface` when the data set does
        not carry the field directly

    Returns
    -------
    coord : xarray.DataArray
        The elevation of ``ds[var_name]``, in m, positive up, on
        ``nCells`` and the vertical dimension appropriate to ``location``.
        A ``Time`` dimension of length one is retained if present.
        ``var_name`` is ``zMid``, ``GeomZInterface`` or ``zTop`` for
        ``location`` ``'cell-center'``, ``'cell-interfaces'`` or
        ``'cell-top'``, respectively

    Raises
    ------
    ValueError
        If ``location`` is not one of the supported values, the
        corresponding field is not present in the dataset and it may not
        be reconstructed, or ``ds`` has a ``Time`` dimension of length
        other than one
    """
    if location not in _VERT_COORD_VAR_NAMES:
        raise ValueError(
            f'Unsupported variable location {location!r}, expected one of '
            f'{sorted(_VERT_COORD_VAR_NAMES)}'
        )
    var_name = _VERT_COORD_VAR_NAMES[location]
    if var_name in ds:
        coord = ds[var_name]
        if 'Time' in coord.dims and ds.sizes['Time'] != 1:
            raise ValueError(
                'vertical_coord_from_location() requires ds to have no '
                'Time dimension or a Time dimension of length one'
            )
        return coord
    if not allow_reconstruct:
        raise ValueError(
            f'{var_name} ({location}) is not present in the dataset'
        )
    z_mid, z_interface = _reconstruct_z_mid_and_interface(ds)
    if location == 'cell-center':
        coord = z_mid
    elif location == 'cell-interfaces':
        coord = z_interface
    else:
        coord = z_interface.isel(nVertLevelsP1=slice(0, -1)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )
    return coord


def location_for_field(var, field_name=None):
    """
    The variable location of ``var`` to look up its vertical coordinate

    A field on ``nVertLevelsP1`` is defined at layer interfaces --- the top
    of each layer, plus one more for the bottom of the column.  A field
    listed under ``variables_at_layer_tops`` in ``variables.yaml`` is
    defined at the top of each layer but written on ``nVertLevels``.
    Everything else is a layer quantity, defined at layer midpoints.

    Parameters
    ----------
    var : xarray.DataArray
        The field to plot or analyze

    field_name : str, optional
        The name of ``var`` in its dataset, used to check whether it is a
        layer-top field

    Returns
    -------
    location : {'cell-center', 'cell-interfaces', 'cell-top'}
        The variable location suitable for
        :py:func:`vertical_coord_from_location`
    """
    if 'nVertLevelsP1' in var.dims:
        return 'cell-interfaces'
    if field_name in _variables_at_layer_tops():
        return 'cell-top'
    return 'cell-center'


def _z_from_thickness(
    layer_thickness, bottom_depth, min_level_cell, max_level_cell
):
    """
    Compute z at layer interfaces and midpoints from layer thickness,
    anchored at ``bottom_depth`` and summed upward from the seafloor.

    This is the shared core used both by
    :py:func:`polaris.ocean.vertical.compute_zint_zmid_from_layer_thickness`,
    which builds the vertical coordinate at init time, and by
    :py:func:`_reconstruct_z_mid_and_interface`, which reconstructs it for
    analysis when a simulation did not write it.

    Parameters
    ----------
    layer_thickness : xarray.DataArray
        The layer thickness of each layer

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor

    min_level_cell : xarray.DataArray
        The zero-based minimum vertical index of each column

    max_level_cell : xarray.DataArray
        The zero-based maximum vertical index of each column

    Returns
    -------
    z_mid : xarray.DataArray
        The elevation of layer midpoints, in m, positive up

    z_interface : xarray.DataArray
        The elevation of layer interfaces, in m, positive up
    """
    n_vert_levels = layer_thickness.sizes['nVertLevels']

    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mask_mid = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    )

    dz = layer_thickness.where(mask_mid, 0.0)
    dz_rev = dz.isel(nVertLevels=slice(None, None, -1))
    sum_from_level = dz_rev.cumsum(dim='nVertLevels').isel(
        nVertLevels=slice(None, None, -1)
    )

    z_bot = (
        xr.zeros_like(layer_thickness.isel(nVertLevels=0, drop=True))
        - bottom_depth
    )
    z_interface_top = z_bot + sum_from_level
    z_interface = z_interface_top.pad(nVertLevels=(0, 1), mode='constant')
    z_interface[dict(nVertLevels=n_vert_levels)] = z_bot
    z_interface = z_interface.rename({'nVertLevels': 'nVertLevelsP1'})

    z_index_p1 = xr.DataArray(
        np.arange(n_vert_levels + 1), dims=['nVertLevelsP1']
    )
    mask_interface = np.logical_and(
        z_index_p1 >= min_level_cell,
        z_index_p1 - 1 <= max_level_cell,
    )
    z_interface = z_interface.where(mask_interface)

    z_interface_upper = z_interface.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    z_interface_lower = z_interface.isel(nVertLevelsP1=slice(1, None)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    z_mid = (0.5 * (z_interface_upper + z_interface_lower)).where(mask_mid)

    dims = list(layer_thickness.dims)
    interface_dims = [dim for dim in dims if dim != 'nVertLevels']
    interface_dims.append('nVertLevelsP1')
    z_interface = z_interface.transpose(*interface_dims)
    z_mid = z_mid.transpose(*dims)

    return z_mid, z_interface


def _reconstruct_z_mid_and_interface(ds):
    """
    Reconstruct z_mid and z_interface for a dataset that did not write them,
    anchored at ``bottomDepth`` via :py:func:`_z_from_thickness`

    Parameters
    ----------
    ds : xarray.Dataset
        An ocean dataset containing the geometric layer thickness (or the
        fields needed to compute it, see :py:func:`geom_thickness_from_ds`)
        and ``bottomDepth``, and optionally ``minLevelCell``,
        ``maxLevelCell`` and a ``Time`` dimension of length one

    Returns
    -------
    z_mid : xarray.DataArray
        The location in meters from the sea surface of the midpoint of
        each layer (level), positive upward

    z_interface : xarray.DataArray
        The elevation of layer interfaces, in m, positive up

    Raises
    ------
    ValueError
        If ``bottomDepth`` or the geometric layer thickness cannot be
        obtained from the dataset, or if required dimensions are missing
    """
    layer_thickness = geom_thickness_from_ds(ds, config=None)
    if 'bottomDepth' not in ds.keys():
        raise ValueError(
            'Could not reconstruct zMid, GeomZInterface: bottomDepth is '
            'not present in the dataset'
        )
    if 'Time' in ds.dims:
        print('Time dimension present in dataset; using first time index')
        ds = ds.isel(Time=0)
        layer_thickness = layer_thickness.isel(Time=0)
    if 'nCells' not in ds.sizes and 'nVertLevels' not in ds.sizes:
        raise ValueError('nCells, and nVertLevels must be dimensions of ds')

    bottom_depth = ds.bottomDepth
    if 'minLevelCell' in ds.keys():
        min_level_cell = ds.minLevelCell
    else:
        min_level_cell = xr.zeros_like(bottom_depth)
    if 'maxLevelCell' in ds.keys():
        max_level_cell = ds.maxLevelCell
    else:
        max_level_cell = (ds.sizes['nVertLevels'] - 1) * xr.ones_like(
            bottom_depth
        )

    return _z_from_thickness(
        layer_thickness=layer_thickness,
        bottom_depth=bottom_depth,
        min_level_cell=min_level_cell,
        max_level_cell=max_level_cell,
    )
