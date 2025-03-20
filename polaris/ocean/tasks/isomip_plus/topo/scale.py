import os
from typing import List

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step


class TopoScale(Step):
    """
    A step for scaling topography data to create a simple time series of ice
    sheet/shelf load

    Attributes
    ----------
    experiment : {'inception', 'drying', 'wetting'}
        The scaling experiment
    """

    def __init__(self, component, subdir, config, topo_remap, experiment):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory in the test case's work directory for the step

        config : polaris.config.PolarisConfigParser
            A shared config parser

        topo_remap : polaris.ocean.tasks.isomip_plus.topo_map.TopoRemap
            The step that produced the remapped topography to be scaled

        experiment : {'inception', 'drying', 'wetting'}
            The scaling experiment
        """
        if experiment not in ['inception', 'drying', 'wetting']:
            raise ValueError(f'Unexpected experiment {experiment}')

        super().__init__(component=component, name='topo_scale', subdir=subdir)
        self.experiment = experiment

        self.set_shared_config(config, link='isomip_plus_topo.cfg')

        topo_filename = os.path.join(topo_remap.path, 'topography_remapped.nc')
        self.add_input_file(
            filename='topography_unscaled.nc', work_dir_target=topo_filename
        )
        self.add_output_file('topography_remapped.nc')

    def run(self):
        """
        Run this step of the test case
        """
        experiment = self.experiment
        config = self.config

        dates: List[str] = config.getlist(
            'isomip_plus_scaling', f'{experiment}_dates', dtype=str
        )
        dates = [date.ljust(64) for date in dates]
        scales: List[float] = config.getlist(
            'isomip_plus_scaling', f'{experiment}_scales', dtype=float
        )

        ds_orig = xr.open_dataset('topography_unscaled.nc')

        ds_list: List[xr.Dataset] = list()

        for index in range(len(dates)):
            date = dates[index]
            scale = scales[index]
            ds = xr.Dataset(ds_orig)
            ds['xtime'] = date
            for var in ['landIcePressure', 'landIceDraft']:
                ds[var] = ds_orig[var] * scale
            ds_list.append(ds)

        ds = xr.concat(ds_list, dim='Time')
        ds['xtime'] = ds.xtime.astype('|S64')

        write_netcdf(ds, 'topography_remapped.nc', char_dim_name='StrLen')
