import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf

from polaris import Step


class TopoRemap(Step):
    """
    A step for remapping topography data from the ISOMIP+ input grid ot the
    MPAS mesh

    """
    def __init__(self, component, name, subdir, topo_map, experiment):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory in the test case's work directory for the step

        topo_map : polaris.ocean.tasks.isomip_plus.topo_map.TopoMap
            The step for creating a mapping files, also used to remap data
            from the MPAS mesh to a lon-lat grid

        experiment : {'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment
        """
        super().__init__(component=component, name=name, subdir=subdir)

        geom_filenames = dict(
            ocean1='Ocean1_input_geom_v1.01.nc',
            ocean2='Ocean2_input_geom_v1.01.nc',
            ocean3='Ocean3_input_geom_v1.01.nc',
            ocean4='Ocean4_input_geom_v1.01.nc')

        if experiment not in geom_filenames:
            raise ValueError(f'No input geometry for experiment {experiment}')

        self.add_input_file(filename='topography.nc',
                            target=geom_filenames[experiment],
                            database='isomip_plus')
        self.add_dependency(topo_map, name='topo_map')
        self.add_output_file('topography_remapped.nc')

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        topo_map = self.dependencies['topo_map']

        ice_density = self.config.getfloat('isomip_plus', 'ice_density')

        remapper = topo_map.get_remapper()

        with (xr.open_dataset('topography.nc') as ds_in):
            ds_in['iceThickness'] = ds_in.upperSurface - ds_in.lowerSurface
            ds_in.iceThickness.attrs['description'] = 'ice thickness'
            ds_in.iceThickness.attrs['units'] = 'm'

            gravity = constants['SHR_CONST_G']
            ds_in['landIcePressure'] = (ice_density * gravity *
                                        ds_in.iceThickness)
            ds_in.iceThickness.attrs['description'] = \
                'pressure at the ice base'
            ds_in.iceThickness.attrs['units'] = 'Pa'

            ds_in = ds_in.rename({'floatingMask': 'landIceFloatingFraction',
                                  'groundedMask': 'landIceGroundedFraction',
                                  'openOceanMask': 'openOceanFraction',
                                  'lowerSurface': 'landIceDraft'})
            ds_in['oceanFraction'] = \
                (ds_in.bedrockTopography < 0.).astype(float)
            ds_in['landIceFraction'] = (ds_in.landIceFloatingFraction +
                                        ds_in.landIceGroundedFraction)

            ds_in.to_netcdf('topography_processed.nc')

        remapper.remap_file(inFileName='topography_processed.nc',
                            outFileName='topography_ncremap.nc',
                            logger=logger)
        with xr.open_dataset('topography_ncremap.nc') as ds_out:
            drop = ['x', 'y', 'area', 'lat_vertices', 'lon_vertices']
            rename = {'ncol': 'nCells'}
            if 't' in ds_out.dims:
                drop.append('t')
                rename['t'] = 'Time'
            ds_out = ds_out.drop_vars(drop)
            ds_out = ds_out.rename(rename)

            if 'Time' in ds_out.dims:
                xtime = []
                for time_index in range(ds_out.sizes['Time']):
                    time_str = f'{time_index + 1:04d}-01-01_00:00:00'
                    xtime.append(time_str)
                ds_out['xtime'] = ('Time', np.array(xtime, 'S64'))

            write_netcdf(ds_out, 'topography_remapped.nc')
