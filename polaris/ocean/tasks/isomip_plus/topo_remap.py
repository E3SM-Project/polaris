import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step


class TopoRemap(Step):
    """
    A step for remapping topography data from the ISOMIP+ input grid ot the
    MPAS mesh

    """
    def __init__(self, component, subdir, topo_map, experiment):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory in the test case's work directory for the step

        topo_map : polaris.ocean.tasks.isomip_plus.topo_map.TopoMap
            The step for creating a mapping files, also used to remap data
            from the MPAS mesh to a lon-lat grid

        experiment : {'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment
        """
        super().__init__(component=component, name='remap_topo', subdir=subdir)

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

        remapper = topo_map.get_remapper()

        with xr.open_dataset('topography.nc') as ds_in:
            ds_in['domainMask'] = xr.ones_like(ds_in.openOceanMask)
            ds_in['iceThickness'] = ds_in.upperSurface - ds_in.lowerSurface
            ds_in.iceThickness.attrs['description'] = 'ice thickness'
            ds_in.iceThickness.attrs['units'] = 'm'
            ds_in.to_netcdf('topography_processed.nc')

        remapper.remap_file(inFileName='topography_processed.nc',
                            outFileName='topography_ncremap.nc',
                            logger=logger)
        with xr.open_dataset('topography_ncremap.nc') as ds_out:
            ds_out = ds_out.rename({'ncol': 'nCells'})
            write_netcdf(ds_out, 'topography_remapped.nc')
