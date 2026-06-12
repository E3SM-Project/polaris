import csv

import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.model import get_days_since_start


def compute_rpe(ds_mesh, ds_init, ds_outputs, config=None, ds_vert_coord=None):
    """
    Computes the reference (resting) potential energy for the whole domain

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        Dataset containing MPAS horizontal mesh variables

    ds_init : xarray.Dataset
        Dataset containing the initial state

    ds_outputs : list of xarray.Dataset
        Datasets containing output of forward steps

    config : polaris.config.PolarisConfigParser, optional
        Configuration for the task

    ds_vert_coord : xarray.Dataset, optional
        Dataset containing vertical-coordinate variables (``bottomDepth``,
        ``minLevelCell``, ``maxLevelCell``).  For Omega this is the separate
        ``vert_coord.nc`` dataset opened via
        :py:meth:`~polaris.ocean.model.OceanIOStep.open_vert_coord_dataset`.
        Defaults to *ds_init* when not provided (correct for MPAS-Ocean).

    Returns
    -------
    rpe : numpy.ndarray
        the reference potential energy of size ``len(output_files)`` x
        ``Time``
    """
    if ds_vert_coord is None:
        ds_vert_coord = ds_init

    num_files = len(ds_outputs)
    if num_files == 0:
        raise ValueError('Must provide at least one output filename')

    gravity = get_constant('standard_acceleration_of_gravity')

    xEdge = ds_mesh.xEdge
    yEdge = ds_mesh.yEdge
    areaCell = ds_mesh.areaCell
    minLevelCell = ds_vert_coord.minLevelCell - 1
    maxLevelCell = ds_vert_coord.maxLevelCell - 1
    bottomDepth = ds_vert_coord.bottomDepth
    nVertLevels = ds_init.sizes['nVertLevels']

    areaCellMatrix = np.tile(areaCell, (nVertLevels, 1)).transpose()
    bottomMax = np.max(bottomDepth.values)
    yMin = np.min(yEdge.values)
    yMax = np.max(yEdge.values)
    xMin = np.min(xEdge.values)
    xMax = np.max(xEdge.values)
    areaDomain = (yMax - yMin) * (xMax - xMin)

    vert_index = xr.DataArray.from_dict(
        {'dims': ('nVertLevels',), 'data': np.arange(nVertLevels)}
    )

    cell_mask = np.logical_and(
        vert_index >= minLevelCell, vert_index <= maxLevelCell
    )
    cell_mask = np.swapaxes(cell_mask, 0, 1)

    nt = max(ds.sizes['Time'] for ds in ds_outputs)
    rpe = np.ones((num_files, nt)) * np.nan

    for file_index, ds in enumerate(ds_outputs):
        if ds.sizes['Time'] == nt:
            days = get_days_since_start(ds)
        hFull = ds.layerThickness.values
        if 'density' in ds:
            densityFull = ds.density.values
        if 'SpecVol' in ds:
            densityFull = np.divide(1.0, ds.SpecVol.values)

        for time_index in range(ds.sizes['Time']):
            h = hFull[time_index, :, :]
            vol = np.multiply(h, areaCellMatrix)
            density = densityFull[time_index, :, :]
            density_1D = density[cell_mask]
            vol_1D = vol[cell_mask]

            # Density sorting in ascending order
            sorted_ind = np.argsort(density_1D)
            density_sorted = density_1D[sorted_ind]
            vol_sorted = vol_1D[sorted_ind]

            thickness = np.divide(vol_sorted.tolist(), areaDomain)

            # RPE computation
            z = np.append([0.0], -np.cumsum(thickness))
            zMid = z[0:-1] - 0.5 * thickness + bottomMax
            rpe1 = gravity * np.multiply(
                np.multiply(density_sorted, zMid), vol_sorted
            )

            rpe[file_index, time_index] = np.sum(rpe1) / np.sum(areaCell)

    with open('rpe.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        headers = ['time'] + [
            f'output_{index + 1}' for index in range(num_files)
        ]
        writer.writerow(headers)
        for time_index in range(nt):
            time = days[time_index]
            row = [time] + [f'{rpe_val:g}' for rpe_val in rpe[:, time_index]]
            writer.writerow(row)

    return rpe
