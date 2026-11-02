"""
Diagnostics of ice-shelf melt, the drivers of melt, and a thin film under
grounded ice, on MPAS-Ocean's names

Each function takes fields with or without a ``Time`` dimension and keeps
it.  Monthly means are first renamed with
:py:func:`polaris.mpas.time_series_stats.rename_time_series_stats`.
"""

import numpy as np
import xarray as xr
from scipy.spatial import KDTree

from polaris.constants import get_constant


def compute_melt_rate(fresh_water_flux):
    """
    Compute the melt rate from the land-ice freshwater flux

    Parameters
    ----------
    fresh_water_flux : xarray.DataArray
        ``landIceFreshwaterFlux`` (kg m-2 s-1), per unit area of the cell

    Returns
    -------
    melt_rate : xarray.DataArray
        The melt rate (m s-1) of freshwater per unit area of the cell,
        positive for melting
    """
    melt_rate = fresh_water_flux / get_constant('pure_water_density_reference')
    melt_rate.attrs = dict(long_name='melt rate', units='m s-1')
    return melt_rate


def compute_thermal_driving(ds):
    """
    Compute the thermal driving of melt, the boundary-layer temperature less
    the interface temperature

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``landIceBoundaryLayerTemperature`` and
        ``landIceInterfaceTemperature``

    Returns
    -------
    thermal_driving : xarray.DataArray
        The thermal driving (degC)
    """
    driving = (
        ds.landIceBoundaryLayerTemperature - ds.landIceInterfaceTemperature
    )
    driving.attrs = dict(long_name='thermal driving', units='degC')
    return driving


def compute_haline_driving(ds):
    """
    Compute the haline driving of melt, the boundary-layer salinity less
    the interface salinity

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``landIceBoundaryLayerSalinity`` and
        ``landIceInterfaceSalinity``

    Returns
    -------
    haline_driving : xarray.DataArray
        The haline driving (PSU)
    """
    driving = ds.landIceBoundaryLayerSalinity - ds.landIceInterfaceSalinity
    driving.attrs = dict(long_name='haline driving', units='PSU')
    return driving


def compute_melt_diagnostics(
    area_cell, ds, floating_fraction, draft=None, deep_draft=-300.0
):
    """
    Compute the total melt flux and the means of melt and its drivers over
    the floating ice base

    Partly floating cells melt only over their floating fraction, so the
    means are weighted by the floating area of each cell.

    Parameters
    ----------
    area_cell : xarray.DataArray
        The area of each cell (m2)

    ds : xarray.Dataset
        A dataset with ``landIceFreshwaterFlux``,
        ``landIceFrictionVelocity`` and the boundary-layer and interface
        temperature and salinity, and optionally
        ``frazilIceFreshwaterFlux``

    floating_fraction : xarray.DataArray
        ``landIceFloatingFraction``

    draft : xarray.DataArray, optional
        The elevation of the ice base (m, negative below sea level).  If
        given, the mean melt rate where the draft is deeper than
        ``deep_draft`` is also computed.

    deep_draft : float, optional
        The draft (m) below which the deep mean melt rate is taken

    Returns
    -------
    ds_diag : xarray.Dataset
        ``totalMeltFlux`` (kg s-1), ``floatingArea`` (m2),
        ``meanMeltRate`` (m s-1), ``meanThermalDriving`` (degC),
        ``meanHalineDriving`` (PSU), ``meanFrictionVelocity`` (m s-1),
        with a draft, ``meanMeltRateDeep`` (m s-1) and, with
        ``frazilIceFreshwaterFlux``, ``totalFrazilFlux`` (kg s-1), the
        freshwater flux from frazil formed under the ice shelf, negative
        where frazil forms.  The melt flux leaves frazil out.
    """
    floating_area = floating_fraction * area_cell
    melt_rate = compute_melt_rate(ds.landIceFreshwaterFlux)

    ds_diag = xr.Dataset()
    ds_diag['totalMeltFlux'] = (ds.landIceFreshwaterFlux * area_cell).sum(
        dim='nCells'
    )
    ds_diag['floatingArea'] = floating_area.sum(dim='nCells')
    ds_diag['meanMeltRate'] = _area_sum(melt_rate, area_cell) / _area_sum(
        floating_fraction, area_cell
    )
    for name, field in [
        ('meanThermalDriving', compute_thermal_driving(ds)),
        ('meanHalineDriving', compute_haline_driving(ds)),
        ('meanFrictionVelocity', ds.landIceFrictionVelocity),
    ]:
        ds_diag[name] = _weighted_mean(field, floating_area)
    if draft is not None:
        deep = draft < deep_draft
        ds_diag['meanMeltRateDeep'] = _area_sum(
            melt_rate.where(deep, 0.0), area_cell
        ) / _area_sum(floating_fraction.where(deep, 0.0), area_cell)
    if 'frazilIceFreshwaterFlux' in ds:
        under_ice = floating_fraction > 0.0
        ds_diag['totalFrazilFlux'] = _area_sum(
            ds.frazilIceFreshwaterFlux.where(under_ice, 0.0), area_cell
        )

    attrs = dict(
        totalMeltFlux=('total melt flux', 'kg s-1'),
        floatingArea=('floating area', 'm2'),
        meanMeltRate=('mean melt rate over the ice base', 'm s-1'),
        meanThermalDriving=('mean thermal driving', 'degC'),
        meanHalineDriving=('mean haline driving', 'PSU'),
        meanFrictionVelocity=('mean friction velocity', 'm s-1'),
        meanMeltRateDeep=(
            f'mean melt rate where the draft is below {deep_draft:g} m',
            'm s-1',
        ),
        totalFrazilFlux=(
            'total freshwater flux from frazil under the ice shelf',
            'kg s-1',
        ),
    )
    for var in ds_diag.data_vars.values():
        long_name, units = attrs[str(var.name)]
        var.attrs = dict(long_name=long_name, units=units)
    return ds_diag


def compute_melt_rate_by_draft(
    area_cell, fresh_water_flux, floating_fraction, draft, bin_width=20.0
):
    """
    Compute the mean melt rate over the ice base in bins of draft

    Parameters
    ----------
    area_cell : xarray.DataArray
        The area of each cell (m2)

    fresh_water_flux : xarray.DataArray
        ``landIceFreshwaterFlux`` (kg m-2 s-1)

    floating_fraction : xarray.DataArray
        ``landIceFloatingFraction``

    draft : xarray.DataArray
        The elevation of the ice base (m, negative below sea level), without
        a ``Time`` dimension

    bin_width : float, optional
        The width (m) of each bin of draft

    Returns
    -------
    ds_bins : xarray.Dataset
        ``meanMeltRate`` (m s-1) and ``floatingArea`` (m2) in each bin, on
        the dimension ``nDraftBins`` with the coordinate ``draft``, each
        bin's center.  Bins without floating ice have a NaN mean.
    """
    floating = (floating_fraction > 0.0).any(
        dim=[dim for dim in floating_fraction.dims if dim != 'nCells']
    )
    deepest = float(draft.where(floating).min())
    edges = bin_width * np.arange(np.floor(deepest / bin_width), 1.0)
    centers = 0.5 * (edges[:-1] + edges[1:])
    melt_rate = compute_melt_rate(fresh_water_flux)

    means = []
    areas = []
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        in_bin = np.logical_and(draft >= lower, draft < upper)
        area = _area_sum(floating_fraction.where(in_bin, 0.0), area_cell)
        melt = _area_sum(melt_rate.where(in_bin, 0.0), area_cell)
        means.append(melt / area.where(area > 0.0))
        areas.append(area)
    ds_bins = xr.Dataset()
    ds_bins['meanMeltRate'] = xr.concat(means, dim='nDraftBins')
    ds_bins['floatingArea'] = xr.concat(areas, dim='nDraftBins')
    ds_bins.coords['draft'] = ('nDraftBins', centers)
    ds_bins.meanMeltRate.attrs = dict(
        long_name='mean melt rate over the ice base', units='m s-1'
    )
    ds_bins.floatingArea.attrs = dict(long_name='floating area', units='m2')
    ds_bins.draft.attrs = dict(long_name='draft', units='m')
    return ds_bins


def compute_thin_film_diagnostics(
    area_cell,
    ssh,
    bottom_depth,
    level_count,
    land_ice_fraction,
    floating_fraction,
    min_thickness,
):
    """
    Compute the area of thin film under grounded ice and the mean sea-surface
    height of the open ocean

    A column is dry if it is less than twice the minimum thickness of each
    of its active layers.

    Parameters
    ----------
    area_cell : xarray.DataArray
        The area of each cell (m2)

    ssh : xarray.DataArray
        The sea-surface height (m)

    bottom_depth : xarray.DataArray
        The depth of the seafloor (m, positive down)

    level_count : xarray.DataArray
        The number of active layers in each column

    land_ice_fraction : xarray.DataArray
        ``landIceFraction``

    floating_fraction : xarray.DataArray
        ``landIceFloatingFraction``

    min_thickness : float
        The minimum thickness (m) of a layer, the namelist option
        ``config_drying_min_cell_height``

    Returns
    -------
    ds_diag : xarray.Dataset
        ``dryAreaUnderGroundedIce`` (m2) and ``openOceanMeanSsh`` (m)
    """
    column_thickness = ssh + bottom_depth
    dry = column_thickness < 2.0 * min_thickness * level_count
    grounded = np.logical_and(
        land_ice_fraction > 0.0, floating_fraction == 0.0
    )
    open_ocean = land_ice_fraction == 0.0

    ds_diag = xr.Dataset()
    ds_diag['dryAreaUnderGroundedIce'] = area_cell.where(
        np.logical_and(dry, grounded), 0.0
    ).sum(dim='nCells')
    ds_diag['openOceanMeanSsh'] = _weighted_mean(
        ssh, area_cell.where(open_ocean, 0.0)
    )
    ds_diag.dryAreaUnderGroundedIce.attrs = dict(
        long_name='area of dry columns under grounded ice', units='m2'
    )
    ds_diag.openOceanMeanSsh.attrs = dict(
        long_name='mean sea-surface height of the open ocean', units='m'
    )
    return ds_diag


def compute_grounding_line_band_diagnostics(
    area_cell,
    x_cell,
    y_cell,
    fresh_water_flux,
    floating_fraction,
    coupled_floating_fraction,
    min_floating_fraction,
):
    """
    Compute how much of the land-ice model's floating ice the ocean treats
    as grounded, in cells next to the grounding line, and an estimate of
    the melt the ocean misses there

    A cell is in the band if the land-ice model floats more than the
    minimum fraction of it but the ocean holds its column at the thin film,
    with no floating fraction of its own.  The melt missed in a band cell is
    its floating area under the land-ice model times the melt rate per
    floating area of the nearest melting cell.  Cells next to the grounding
    line generally melt less, so the estimate is likely an upper bound.

    Parameters
    ----------
    area_cell : xarray.DataArray
        The area of each cell (m2)

    x_cell : xarray.DataArray
        The x coordinate of each cell center (m)

    y_cell : xarray.DataArray
        The y coordinate of each cell center (m)

    fresh_water_flux : xarray.DataArray
        ``landIceFreshwaterFlux`` (kg m-2 s-1), per unit area of the cell

    floating_fraction : xarray.DataArray
        ``landIceFloatingFraction``, the ocean's floating fraction

    coupled_floating_fraction : xarray.DataArray
        ``landIceGlcFloatingFraction``, the floating fraction the ocean
        receives from the land-ice model

    min_floating_fraction : float
        The land-ice model's floating fraction above which the ocean and
        land-ice model exchange melt, the namelist option
        ``config_glc_ice_shelf_coupling_min_floating_fraction``

    Returns
    -------
    ds_diag : xarray.Dataset
        ``bandFloatingArea`` and ``coupledFloatingArea`` (m2), their ratio
        ``bandFloatingAreaFraction``, ``bandMissedMeltFlux`` (kg s-1) and
        its ratio to the total melt flux, ``bandMissedMeltFraction``
    """
    fresh_water_flux, floating_fraction, coupled_floating_fraction = (
        xr.broadcast(
            fresh_water_flux, floating_fraction, coupled_floating_fraction
        )
    )
    has_time = 'Time' in fresh_water_flux.dims
    if not has_time:
        fresh_water_flux = fresh_water_flux.expand_dims('Time')
        floating_fraction = floating_fraction.expand_dims('Time')
        coupled_floating_fraction = coupled_floating_fraction.expand_dims(
            'Time'
        )
    names = [
        'bandFloatingArea',
        'coupledFloatingArea',
        'bandMissedMeltFlux',
        'totalMeltFlux',
    ]
    values: dict[str, list[float]] = {name: [] for name in names}
    area = area_cell.values
    points = np.column_stack([x_cell.values, y_cell.values])
    for t_index in range(fresh_water_flux.sizes['Time']):
        melt = fresh_water_flux.isel(Time=t_index).values
        ocean = floating_fraction.isel(Time=t_index).values
        coupled = coupled_floating_fraction.isel(Time=t_index).values
        band = np.logical_and(ocean == 0.0, coupled > min_floating_fraction)
        band_area = area[band] * coupled[band]
        melting = np.logical_and(melt > 0.0, ocean > 0.0)
        missed = 0.0
        if band.any() and melting.any():
            rate = melt[melting] / ocean[melting]
            _, nearest = KDTree(points[melting]).query(points[band])
            missed = float(np.sum(band_area * rate[nearest]))
        values['bandFloatingArea'].append(float(np.sum(band_area)))
        values['coupledFloatingArea'].append(float(np.sum(area * coupled)))
        values['bandMissedMeltFlux'].append(missed)
        values['totalMeltFlux'].append(float(np.sum(area * melt)))

    ds_diag = xr.Dataset()
    for name in names[:3]:
        ds_diag[name] = ('Time', np.array(values[name]))
    total = np.array(values['totalMeltFlux'])
    ds_diag['bandFloatingAreaFraction'] = (
        ds_diag.bandFloatingArea / ds_diag.coupledFloatingArea
    )
    ds_diag['bandMissedMeltFraction'] = ds_diag.bandMissedMeltFlux / (
        xr.DataArray(total, dims='Time').where(total != 0.0)
    )
    if not has_time:
        ds_diag = ds_diag.isel(Time=0)
    ds_diag.bandFloatingArea.attrs = dict(
        long_name=(
            "the land-ice model's floating area in cells the ocean treats "
            'as grounded'
        ),
        units='m2',
    )
    ds_diag.coupledFloatingArea.attrs = dict(
        long_name="the land-ice model's floating area", units='m2'
    )
    ds_diag.bandMissedMeltFlux.attrs = dict(
        long_name='estimated melt flux missed in the grounding-line band',
        units='kg s-1',
    )
    ds_diag.bandFloatingAreaFraction.attrs = dict(
        long_name=(
            "fraction of the land-ice model's floating area that the ocean "
            'treats as grounded'
        ),
        units='1',
    )
    ds_diag.bandMissedMeltFraction.attrs = dict(
        long_name=(
            'estimated melt missed in the grounding-line band, as a '
            'fraction of the total melt'
        ),
        units='1',
    )
    return ds_diag


def _area_sum(field, area_cell):
    """Sum a field per unit area over the cells"""
    return (field * area_cell).sum(dim='nCells')


def _weighted_mean(field, weights):
    """Average a field over the cells with the given weights"""
    return (field * weights).sum(dim='nCells') / weights.sum(dim='nCells')
