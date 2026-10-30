import os

import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.step import Step
from polaris.tasks.e3sm.init.misomip.land_ice_fields import (
    compute_land_ice_fields,
    read_map,
)

#: The time of the land-ice fields of an experiment whose geometry is fixed
STATIC_XTIME = '0001-01-01_00:00:00'

#: The number of data-mode records to process at once
RECORD_CHUNK = 100


class LandIceOnOceanStep(Step):
    """
    A step for computing the ocean's land-ice pressure and fractions from
    MALI's geometry, as E3SM's coupler delivers them, for each of MALI's
    records

    Attributes
    ----------
    data_mode : bool
        Whether MALI replays its geometry from a data-mode file
    """

    def __init__(
        self,
        component,
        subdir,
        landice_init_step,
        map_step,
        landice_data_step=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        landice_init_step : polaris.Step
            The step that makes MALI's initial condition

        map_step : polaris.Step
            The step that makes the conservative map from MALI to the ocean

        landice_data_step : polaris.Step, optional
            The step that makes MALI's data-mode file, if there is one
        """
        super().__init__(
            component=component, name='land_ice_on_ocean', subdir=subdir
        )
        self.data_mode = landice_data_step is not None
        self.add_input_file(
            filename='landice_init.nc',
            work_dir_target=os.path.join(
                landice_init_step.path, 'landice_init.nc'
            ),
        )
        self.add_input_file(
            filename='map.nc',
            work_dir_target=os.path.join(map_step.path, 'map.nc'),
        )
        if landice_data_step is not None:
            self.add_input_file(
                filename='landice_datamode.nc',
                work_dir_target=os.path.join(
                    landice_data_step.path, 'landice_datamode.nc'
                ),
            )
        self.add_output_file(filename='land_ice_fields.nc')

    def run(self):
        """
        Run this step
        """
        matrix = read_map('map.nc')
        with xr.open_dataset('landice_init.nc') as ds_init:
            bed = ds_init.bedTopography.isel(Time=0).values
            thickness = ds_init.thickness.isel(Time=0).values

        if self.data_mode:
            fields, xtimes = _fields_from_data_mode(matrix, bed)
        else:
            fields = compute_land_ice_fields(
                matrix, thickness[np.newaxis, :], bed
            )
            xtimes = [STATIC_XTIME]

        self.logger.info(
            f'Land-ice fields for {len(xtimes)} records, from {xtimes[0]} '
            f'to {xtimes[-1]}'
        )
        ds = xr.Dataset()
        ds['xtime'] = (
            'Time',
            np.array([xtime.ljust(64) for xtime in xtimes], dtype='S64'),
        )
        for name, field in fields.items():
            ds[name] = (('Time', 'nCells'), field)
        ds.landIcePressure.attrs['units'] = 'Pa'
        write_netcdf(ds, 'land_ice_fields.nc', char_dim_name='StrLen')


def _fields_from_data_mode(matrix, bed):
    """
    Compute the land-ice fields for every record of MALI's data-mode file,
    a chunk of records at a time
    """
    fields: dict[str, list[np.ndarray]] = dict()
    with netCDF4.Dataset('landice_datamode.nc') as ds:
        xtimes = [
            str(xtime).strip()
            for xtime in netCDF4.chartostring(ds.variables['xtime'][:])
        ]
        record_count = len(xtimes)
        for start in range(0, record_count, RECORD_CHUNK):
            stop = min(start + RECORD_CHUNK, record_count)
            thickness = np.asarray(ds.variables['thickness'][start:stop, :])
            chunk = compute_land_ice_fields(matrix, thickness, bed)
            for name, field in chunk.items():
                fields.setdefault(name, []).append(field)
    combined = {
        name: np.concatenate(chunks, axis=0) for name, chunks in fields.items()
    }
    return combined, xtimes
