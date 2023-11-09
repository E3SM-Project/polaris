import os

import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf

from polaris.step import Step


class Forcing(Step):
    """
    A step for creating forcing files for ISOMIP+ experiments

    Attributes
    ----------
    resolution : float
        The horizontal resolution (km) of the test case

    experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
        The ISOMIP+ experiment

    vertical_coordinate : str
        The type of vertical coordinate (``z-star``, ``z-level``, etc.)

    thin_film: bool
        Whether the run includes a thin film below grounded ice
    """
    def __init__(self, component, indir, culled_mesh, topo, resolution,
                 experiment, vertical_coordinate, thin_film):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component this step belongs to

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        culled_mesh : polaris.Step
            The step that culled the MPAS mesh

        topo : polaris.Step
            The step with topography data on the culled mesh

        resolution : float
            The horizontal resolution (km) of the test case

        experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment

        vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

        thin_film: bool
            Whether the run includes a thin film below grounded ice
        """
        super().__init__(component=component, name='forcing', indir=indir)
        self.resolution = resolution
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.thin_film = thin_film

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=os.path.join(culled_mesh.path, 'culled_mesh.nc'))

        self.add_input_file(
            filename='topo.nc',
            work_dir_target=os.path.join(topo.path, 'topography_remapped.nc'))

        self.add_input_file(filename='init.nc', target='../init/init.nc')

        self.add_output_file('init.nc')

    def run(self):
        """
        Create restoring and other forcing files
        """
        self._compute_restoring()

    def _compute_restoring(self):
        config = self.config
        experiment = self.experiment

        ref_density = constants['SHR_CONST_RHOSW']

        ds_mesh = xr.open_dataset('mesh.nc')
        ds_init = xr.open_dataset('init.nc')

        ds_forcing = xr.Dataset()

        section = config['isomip_plus']
        if experiment in ['ocean0', 'ocean1', 'ocean3']:
            top_temp = section.getfloat('warm_top_temp')
            bot_temp = section.getfloat('warm_bot_temp')
            top_sal = section.getfloat('warm_top_sal')
            bot_sal = section.getfloat('warm_bot_sal')
        else:
            top_temp = section.getfloat('cold_top_temp')
            bot_temp = section.getfloat('cold_bot_temp')
            top_sal = section.getfloat('cold_top_sal')
            bot_sal = section.getfloat('cold_bot_sal')

        section = config['isomip_plus_forcing']
        restore_rate = section.getfloat('restore_rate')
        restore_xmin = section.getfloat('restore_xmin')
        restore_xmax = section.getfloat('restore_xmax')
        restore_evap_rate = section.getfloat('restore_evap_rate')

        max_bottom_depth = -config.getfloat('vertical_grid', 'bottom_depth')
        z_frac = (0. - ds_init.zMid) / (0. - max_bottom_depth)

        ds_forcing['temperatureInteriorRestoringValue'] = \
            (1.0 - z_frac) * top_temp + z_frac * bot_temp
        ds_forcing['salinityInteriorRestoringValue'] = \
            (1.0 - z_frac) * top_sal + z_frac * bot_sal

        x_frac = np.maximum(
            ((ds_mesh.xIsomipCell - restore_xmin) /
             (restore_xmax - restore_xmin)),
            0.)
        x_frac = x_frac.broadcast_like(
            ds_forcing.temperatureInteriorRestoringValue)

        # convert from 1/days to 1/s
        ds_forcing['temperatureInteriorRestoringRate'] = \
            x_frac * restore_rate / constants['SHR_CONST_CDAY']
        ds_forcing['salinityInteriorRestoringRate'] = \
            ds_forcing.temperatureInteriorRestoringRate

        # compute "evaporation"
        mask = np.logical_and(ds_mesh.xIsomipCell >= restore_xmin,
                              ds_mesh.xIsomipCell <= restore_xmax)
        mask = mask.expand_dims(dim='Time', axis=0)
        # convert to m/s, negative for evaporation rather than precipitation
        evap_rate = -restore_evap_rate / (constants['SHR_CONST_CDAY'] * 365)
        # PSU*m/s to kg/m^2/s
        sflux_factor = 1.
        # C*m/s to W/m^2
        hflux_factor = 1. / (ref_density * constants['SHR_CONST_CPSW'])
        ds_forcing['evaporationFlux'] = mask * ref_density * evap_rate
        ds_forcing['seaIceSalinityFlux'] = \
            mask * evap_rate * top_sal / sflux_factor
        ds_forcing['seaIceHeatFlux'] = \
            mask * evap_rate * top_temp / hflux_factor

        if self.vertical_coordinate == 'single-layer':
            x_max = np.max(ds_mesh.xIsomipCell.values)
            ds_forcing['tidalInputMask'] = xr.where(
                ds_mesh.xIsomipCell > (x_max - 0.6 * self.resolution * 1e3),
                1.0, 0.0)
        else:
            ds_forcing['tidalInputMask'] = xr.zeros_like(ds_mesh.xIsomipCell)

        write_netcdf(ds_forcing, 'init_mode_forcing_data.nc')
