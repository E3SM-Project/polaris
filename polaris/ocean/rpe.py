import csv

import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants


def compute_rpe(mesh_filename, initial_state_filename, output_filenames):
    """
    Computes the reference (resting) potential energy for the whole domain

    Parameters
    ----------
    mesh_filename : str
        Name of the netCDF file containing the MPAS horizontal mesh variables

    initial_state_filename : str
        Name of the netCDF file containing the initial state

    output_filenames : list
        List of netCDF files containing output of forward steps

    Returns
    -------
    rpe : numpy.ndarray
        the reference potential energy of size ``Time`` x ``len(output_files)``
    """
    num_files = len(output_filenames)
    if num_files == 0:
        raise ValueError('Must provide at least one output filename')

    gravity = constants['SHR_CONST_G']

    ds_mesh = xr.open_dataset(mesh_filename)
    ds_init = xr.open_dataset(initial_state_filename)
    nVertLevels = ds_init.sizes['nVertLevels']

    xEdge = ds_mesh.xEdge
    yEdge = ds_mesh.yEdge
    areaCell = ds_mesh.areaCell
    minLevelCell = ds_init.minLevelCell - 1
    maxLevelCell = ds_init.maxLevelCell - 1
    bottomDepth = ds_init.bottomDepth

    areaCellMatrix = np.tile(areaCell, (nVertLevels, 1)).transpose()
    bottomMax = np.max(bottomDepth.values)
    yMin = np.min(yEdge.values)
    yMax = np.max(yEdge.values)
    xMin = np.min(xEdge.values)
    xMax = np.max(xEdge.values)
    areaDomain = (yMax - yMin) * (xMax - xMin)

    vert_index = \
        xr.DataArray.from_dict({'dims': ('nVertLevels',),
                                'data': np.arange(nVertLevels)})

    cell_mask = np.logical_and(vert_index >= minLevelCell,
                               vert_index <= maxLevelCell)
    cell_mask = np.swapaxes(cell_mask, 0, 1)

    with xr.open_dataset(output_filenames[0]) as ds:
        nt = ds.sizes['Time']
        xtime = ds.xtime.values

    rpe = np.ones((num_files, nt))

    for file_index, out_filename in enumerate(output_filenames):

        ds = xr.open_dataset(out_filename)

        xtime = ds.xtime.values
        hFull = ds.layerThickness
        densityFull = ds.density

        for time_index in range(nt):

            h = hFull[time_index, :, :].values
            vol = np.multiply(h, areaCellMatrix)
            density = densityFull[time_index, :, :].values
            density_1D = density[cell_mask]
            vol_1D = vol[cell_mask]

            # Density sorting in ascending order
            sorted_ind = np.argsort(density_1D)
            density_sorted = density_1D[sorted_ind]
            vol_sorted = vol_1D[sorted_ind]

            thickness = np.divide(vol_sorted.tolist(), areaDomain)

            # RPE computation
            z = np.append([0.], -np.cumsum(thickness))
            zMid = z[0:-1] - 0.5 * thickness + bottomMax
            rpe1 = gravity * np.multiply(
                np.multiply(density_sorted, zMid),
                vol_sorted)

            rpe[file_index, time_index] = np.sum(rpe1) / np.sum(areaCell)

        ds.close()

    with open('rpe.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        headers = ['time'] + \
            [f'output_{index + 1}' for index in range(num_files)]
        writer.writerow(headers)
        for time_index in range(nt):
            time = xtime[time_index].astype(str)
            row = [time] + [f'{rpe_val:g}' for rpe_val in rpe[:, time_index]]
            writer.writerow(row)

    return rpe
