"""
Checks of a MISOMIP run's health, reduced one year at a time: the days a
cell is very fast, the salt above anything the run starts with or restores
to, and the dry columns under the ice
"""

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

#: The fraction of a cell that floats for it to count as partly floating
#: in the salt check: more than this and less than one less this
PARTLY_FLOATING = 0.01

#: How far above the source's maximum salinity a cell is counted as salty
#: (PSU)
SALTY_MARGIN = 0.1

#: How far above the minimum thickness of wetting and drying every layer of
#: a dry column may be, as a fraction of the minimum
DRY_TOLERANCE = 0.1

#: The deficits of dry columns that are counted (m)
DEFICIT_THRESHOLDS = [1.0, 5.0, 10.0]

#: The number of dry columns with the largest deficits that are kept
LARGEST_DEFICITS = 5

#: MPAS's gravity (m s-2), with which the ocean's land-ice pressure is
#: turned back into the column it calls for, as the model does
MPAS_GRAVITY = 9.80616


def get_source_max_salinity(ds_init, ds_restoring=None):
    """
    Get the largest salinity a run starts with or restores to

    Parameters
    ----------
    ds_init : xarray.Dataset
        The initial condition, without a ``Time`` dimension

    ds_restoring : xarray.Dataset, optional
        The interior restoring's fields, if the run restores

    Returns
    -------
    salinity : float
        The largest initial salinity in a layer with water, or restoring
        salinity where the restoring rate is positive (PSU)
    """
    salinity = ds_init.salinity.where(ds_init.layerThickness > 0.0)
    source_max = float(salinity.max())
    if ds_restoring is not None:
        value = ds_restoring.salinityInteriorRestoringValue
        rate = ds_restoring.salinityInteriorRestoringRate
        restored = value.where((rate > 0.0) & (np.abs(value) < 1e30))
        if restored.notnull().any():
            source_max = max(source_max, float(restored.max()))
    return source_max


def compute_spike_cells(kinetic_energy, day_start, speed, ds_init):
    """
    Find the cells whose speed from the day's largest kinetic energy at the
    cell center is above a threshold

    Parameters
    ----------
    kinetic_energy : xarray.DataArray
        The daily maximum of kinetic energy at cell centers, with dimensions
        ``Time``, ``nCells`` and ``nVertLevels``

    day_start : numpy.ndarray
        The start of each day, in days since 0001-01-01

    speed : float
        The speed above which a cell is fast (m s-1)

    ds_init : xarray.Dataset
        The initial condition and mesh, with ``xIsomipCell`` and
        ``yIsomipCell``

    Returns
    -------
    ds : xarray.Dataset
        ``spikeDay``, ``spikeCell`` (0-based), ``spikeX``, ``spikeY`` and
        ``spikeSpeed``, one for each fast cell on each day
    """
    cell_speed = np.sqrt(
        2.0 * np.nan_to_num(kinetic_energy.max(dim='nVertLevels').values)
    )
    days, cells = np.nonzero(cell_speed > speed)
    ds = xr.Dataset()
    ds['spikeDay'] = ('nSpikes', np.asarray(day_start)[days])
    ds.spikeDay.attrs = dict(
        long_name='start of the day', units='days since 0001-01-01'
    )
    ds['spikeCell'] = ('nSpikes', cells.astype(np.int32))
    ds.spikeCell.attrs = dict(long_name='0-based index of the cell')
    _add_cell_coords(ds, 'spike', 'nSpikes', ds_init, cells)
    ds['spikeSpeed'] = ('nSpikes', cell_speed[days, cells])
    ds.spikeSpeed.attrs = dict(
        long_name='speed of the largest kinetic energy at the cell center',
        units='m s-1',
    )
    return ds


def compute_salt_excess(ds, ds_init, source_max, near_distance, front_x):
    """
    The salinity of each month above the run's source maximum, and the
    excess salt in three regions: near the grounding line, the rest under
    the ice shelf, and beyond the ice front

    Parameters
    ----------
    ds : xarray.Dataset
        Monthly means of ``salinity``, ``layerThickness`` and
        ``landIceFloatingFraction``

    ds_init : xarray.Dataset
        The initial condition and mesh

    source_max : float
        The largest salinity the run starts with or restores to (PSU)

    near_distance : float
        How far from a partly floating cell a cell is near the grounding
        line (m)

    front_x : float
        The x of the ice front in the protocol's coordinates (m), at and
        beyond which a cell is beyond the front

    Returns
    -------
    ds_out : xarray.Dataset
        ``maxSalinityExcess``, ``saltyCells`` and the excess salt
        ``saltExcessNearGroundingLine``, ``saltExcessUnderShelf`` and
        ``saltExcessBeyondFront``, each month
    """
    x_cell = ds_init.xIsomipCell.values
    y_cell = ds_init.yIsomipCell.values
    beyond = x_cell >= front_x
    points = np.column_stack([x_cell, y_cell])
    area = ds_init.areaCell.values
    thickness = ds.layerThickness.values
    salinity = ds.salinity.values
    floating = ds.landIceFloatingFraction.values
    valid = (
        (thickness > 0.0)
        & (np.abs(thickness) < 1e30)
        & (np.abs(salinity) < 1e30)
    )
    names = [
        'maxSalinityExcess',
        'saltyCells',
        'saltExcessNearGroundingLine',
        'saltExcessUnderShelf',
        'saltExcessBeyondFront',
    ]
    values: dict = {name: [] for name in names}
    for t_index in range(ds.sizes['Time']):
        h = np.where(valid[t_index], thickness[t_index], 0.0)
        s = np.where(valid[t_index], salinity[t_index], np.nan)
        excess = np.clip(np.nan_to_num(s - source_max), 0.0, None)
        # PSU km3 in each column
        column = 1e-9 * area * (excess * h).sum(axis=1)
        part = (floating[t_index] > PARTLY_FLOATING) & (
            floating[t_index] < 1.0 - PARTLY_FLOATING
        )
        if part.any():
            distance, _ = cKDTree(points[part]).query(points)
            near = distance <= near_distance
        else:
            near = np.zeros(x_cell.shape, dtype=bool)
        values['maxSalinityExcess'].append(float(np.nanmax(s)) - source_max)
        values['saltyCells'].append(
            int(np.any(s > source_max + SALTY_MARGIN, axis=1).sum())
        )
        values['saltExcessNearGroundingLine'].append(column[near].sum())
        values['saltExcessUnderShelf'].append(column[~near & ~beyond].sum())
        values['saltExcessBeyondFront'].append(column[~near & beyond].sum())
    ds_out = xr.Dataset()
    for name in names:
        ds_out[name] = ('Time', np.array(values[name]))
    ds_out.maxSalinityExcess.attrs = dict(
        long_name='largest salinity less the source maximum', units='PSU'
    )
    ds_out.saltyCells.attrs = dict(
        long_name=f'cells with a layer more than {SALTY_MARGIN} PSU above '
        f'the source maximum'
    )
    for name, where in [
        ('saltExcessNearGroundingLine', 'near the grounding line'),
        ('saltExcessUnderShelf', 'under the rest of the ice shelf'),
        ('saltExcessBeyondFront', 'beyond the ice front'),
    ]:
        ds_out[name].attrs = dict(
            long_name=f'salt above the source maximum {where}',
            units='PSU km3',
        )
    return ds_out


def compute_dry_cells(state, ds_init, min_thickness, density):
    """
    A census of the dry columns of a state, every layer at the minimum
    thickness of wetting and drying, with each one's deficit: the column
    the land-ice pressure calls for less its actual column

    Parameters
    ----------
    state : xarray.Dataset
        The state, with ``layerThickness`` and ``landIcePressure`` and no
        ``Time`` dimension

    ds_init : xarray.Dataset
        The initial condition and mesh, with ``bottomDepth``,
        ``minLevelCell``, ``maxLevelCell``, ``xIsomipCell`` and
        ``yIsomipCell``

    min_thickness : float
        The minimum thickness of wetting and drying (m)

    density : float
        The density of the water the land-ice pressure displaces (kg m-3)

    Returns
    -------
    ds : xarray.Dataset
        ``dryCells``, ``dryCellsWithDeficit`` above each of
        ``deficitThreshold``, ``maxDryDeficit``, and the dry cells with the
        largest positive deficits, ``largestDeficitCell`` (0-based, -1 for
        none), ``largestDeficitX``, ``largestDeficitY`` and
        ``largestDeficit``
    """
    gravity = MPAS_GRAVITY
    thickness = state.layerThickness.values
    min_level = ds_init.minLevelCell.values - 1
    max_level = ds_init.maxLevelCell.values
    levels = np.arange(thickness.shape[1])[np.newaxis, :]
    valid = (levels >= min_level[:, np.newaxis]) & (
        levels < max_level[:, np.newaxis]
    )
    ocean = max_level > 0
    column = np.where(valid, thickness, 0.0).sum(axis=1)
    thickest = np.where(valid, thickness, -np.inf).max(axis=1)
    dry = ocean & (thickest <= (1.0 + DRY_TOLERANCE) * min_thickness)
    deficit = (
        ds_init.bottomDepth.values
        - state.landIcePressure.values / (density * gravity)
        - column
    )
    dry_deficit = deficit[dry]
    order = np.flatnonzero(dry)[np.argsort(-dry_deficit)]
    largest = [cell for cell in order[:LARGEST_DEFICITS] if deficit[cell] > 0]
    cells = np.full(LARGEST_DEFICITS, -1, dtype=np.int32)
    deficits = np.full(LARGEST_DEFICITS, np.nan)
    cells[: len(largest)] = largest
    deficits[: len(largest)] = deficit[largest]

    ds = xr.Dataset()
    ds['dryCells'] = int(dry.sum())
    ds.dryCells.attrs = dict(
        long_name='columns with every layer at the minimum thickness'
    )
    ds.coords['deficitThreshold'] = ('nDeficitThresholds', DEFICIT_THRESHOLDS)
    ds.deficitThreshold.attrs = dict(units='m')
    ds['dryCellsWithDeficit'] = (
        'nDeficitThresholds',
        [int((dry_deficit > limit).sum()) for limit in DEFICIT_THRESHOLDS],
    )
    ds.dryCellsWithDeficit.attrs = dict(
        long_name='dry columns with a deficit above each threshold'
    )
    ds['maxDryDeficit'] = (
        float(dry_deficit.max()) if dry_deficit.size else np.nan
    )
    ds.maxDryDeficit.attrs = dict(
        long_name='largest deficit of a dry column', units='m'
    )
    ds['largestDeficitCell'] = ('nLargestDeficits', cells)
    ds.largestDeficitCell.attrs = dict(
        long_name='0-based index of a dry column with a large deficit'
    )
    _add_cell_coords(ds, 'largestDeficit', 'nLargestDeficits', ds_init, cells)
    ds['largestDeficit'] = ('nLargestDeficits', deficits)
    ds.largestDeficit.attrs = dict(
        long_name='deficit of a dry column with a large deficit', units='m'
    )
    return ds


def _add_cell_coords(ds, prefix, dim, ds_init, cells):
    """Add the x and y (km) in the protocol's coordinates of cells, NaN
    where a cell is -1"""
    cells = np.asarray(cells)
    valid = cells >= 0
    for coord in ['x', 'y']:
        values = np.full(cells.shape, np.nan)
        values[valid] = (
            1e-3 * ds_init[f'{coord}IsomipCell'].values[cells[valid]]
        )
        name = f'{prefix}{coord.upper()}'
        ds[name] = (dim, values)
        ds[name].attrs = dict(
            long_name=f"{coord} of the cell in the protocol's coordinates",
            units='km',
        )
