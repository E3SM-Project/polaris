import os

import mpas_tools.io
import netCDF4
import numpy as np
import xarray as xr

from polaris.step import Step
from polaris.tasks.e3sm.init.misomip.calving import calve
from polaris.tasks.e3sm.init.misomip.landice_init import (
    INPUT_FILENAMES,
    remap_input_thickness,
)
from polaris.tasks.e3sm.init.misomip.records import (
    get_interpolation_weights,
    get_monthly_record_times,
)

#: The experiments whose MALI geometry comes from a data-mode file
DATA_MODE_EXPERIMENTS = ['ocean3', 'ocean4']


class LandiceDataStep(Step):
    """
    A step for making MALI's data-mode file for Ocean3 or Ocean4: monthly
    records of thickness, interpolated in time from the protocol's yearly
    geometry and then calved

    Attributes
    ----------
    experiment : str
        The experiment
    """

    def __init__(
        self, component, subdir, experiment, spin_up_step, input_map_step
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        experiment : {'ocean3', 'ocean4'}
            The experiment

        spin_up_step : polaris.Step
            The MISMIP+ step whose output is the steady state

        input_map_step : polaris.Step
            The step that makes the map from the input grid to MALI's mesh
        """
        if experiment not in DATA_MODE_EXPERIMENTS:
            raise ValueError(f'No data-mode file for {experiment}')
        super().__init__(
            component=component, name='landice_data', subdir=subdir
        )
        self.experiment = experiment
        self.add_input_file(
            filename='steady_state.nc',
            work_dir_target=os.path.join(spin_up_step.path, 'steady_state.nc'),
        )
        self.add_input_file(
            filename='input_geometry.nc',
            target=INPUT_FILENAMES[experiment],
            database='isomip_plus',
            database_component='ocean',
        )
        self.add_input_file(
            filename='map.nc',
            work_dir_target=os.path.join(input_map_step.path, 'map.nc'),
        )
        self.add_output_file(filename='landice_datamode.nc')

    def run(self):
        """
        Run this step
        """
        logger = self.logger
        with xr.open_dataset('steady_state.nc') as ds_steady:
            x_cell = ds_steady.xCell.values
            bed = ds_steady.bedTopography.isel(Time=0).values
            steady_thickness = ds_steady.thickness.isel(Time=0).values

        with xr.open_dataset('input_geometry.nc') as ds_input:
            yearly = remap_input_thickness(ds_input, 'map.nc')
            yearly_times = ds_input.t.values
            x = ds_input.x.values
            x_min = x[0] - 0.5 * (x[1] - x[0])

        # upstream of the input, every record holds the steady state
        yearly = np.where(x_cell >= x_min, yearly, steady_thickness)

        year_count = len(yearly_times) - 1
        xtimes, seconds = get_monthly_record_times(year_count)
        before, after, weight = get_interpolation_weights(
            seconds, yearly_times
        )
        logger.info(
            f'Writing {len(xtimes)} monthly records from {len(yearly_times)} '
            f'yearly records'
        )
        write_data_mode_file(
            filename='landice_datamode.nc',
            xtimes=xtimes,
            get_thickness=lambda index: calve(
                (1.0 - weight[index]) * yearly[before[index], :]
                + weight[index] * yearly[after[index], :],
                bed,
                x_cell,
            ),
        )


def write_data_mode_file(filename, xtimes, get_thickness):
    """
    Write MALI's data-mode file one record at a time

    Parameters
    ----------
    filename : str
        The file to write

    xtimes : list of str
        The ``xtime`` of each record

    get_thickness : callable
        A function of the record's index that returns its thickness on
        MALI's cells
    """
    first = np.asarray(get_thickness(0))
    with netCDF4.Dataset(
        filename, 'w', format=mpas_tools.io.default_format
    ) as ds:
        ds.createDimension('Time', None)
        ds.createDimension('nCells', first.size)
        ds.createDimension('StrLen', 64)
        xtime = ds.createVariable('xtime', 'S1', ('Time', 'StrLen'))
        thickness = ds.createVariable('thickness', 'f8', ('Time', 'nCells'))
        thickness.units = 'm'
        thickness.long_name = 'ice thickness'
        for index, value in enumerate(xtimes):
            # padded with null characters, as MALI writes times
            xtime[index, :] = np.frombuffer(
                value.encode().ljust(64, b'\0'), dtype='S1'
            )
            if index == 0:
                thickness[index, :] = first
            else:
                thickness[index, :] = get_thickness(index)
