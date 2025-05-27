import os

import mpas_tools.io
import numpy as np
import xarray as xr
from geometric_features import (
    GeometricFeatures,
    read_feature_collection,
)
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call
from mpas_tools.mesh.mask import compute_mpas_flood_fill_mask
from mpas_tools.ocean.coastline_alteration import (
    add_land_locked_cells_to_mask,
    widen_transect_edge_masks,
)

from polaris import Step


class CullMaskStep(Step):
    """
    A step for creating the masks that will be used to cull land and
    ocean/sea-ice meshes based on critical land and ocean/sea-ice transects,
    handling land-locked cells, and flood-filling to make sure that Antarctic
    land ice and ocean are both contiguous.

    Attributes
    ----------
    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step

    unsmoothed_topo_step : polaris.tasks.e3sm.init.topo.RemapTopoStep
        The step for remapping the topography to the MPAS base mesh without
        smoothing
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        unsmoothed_topo_step,
        name,
        subdir,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The base mesh step containing input files to this step

        unsmoothed_topo_step : polaris.tasks.e3sm.init.topo.RemapTopoStep
            The step for remapping the topography to the MPAS base mesh without
            smoothing

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step
        """
        super().__init__(
            component,
            name=name,
            subdir=subdir,
            cpus_per_task=None,
            min_cpus_per_task=None,
        )
        self.base_mesh_step = base_mesh_step
        self.unsmoothed_topo_step = unsmoothed_topo_step

        self.add_input_file(
            filename='south_pole.geojson',
            package='polaris.tasks.e3sm.init.topo.cull.mask',
        )

        self.add_output_file(filename='cull_masks.nc')

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()
        config = self.config
        section = config['cull_mesh']

        base_path = self.base_mesh_step.path
        base_filename = self.base_mesh_step.config.get(
            'spherical_mesh',
            'mpas_mesh_filename',
        )
        target = os.path.join(base_path, base_filename)
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        topo_filename = 'topography_remapped.nc'

        self.add_input_file(
            filename='topography_unsmoothed.nc',
            work_dir_target=os.path.join(
                self.unsmoothed_topo_step.path, topo_filename
            ),
        )

        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')

    def constrain_resources(self, available_resources):
        """
        Constrain ``cpus_per_task`` and ``ntasks`` based on the number of
        cores available to this step

        Parameters
        ----------
        available_resources : dict
            The total number of cores available to the step
        """
        config = self.config
        section = config['cull_mesh']
        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')
        super().constrain_resources(available_resources)

    def define_critical_land_transects(self, gf):
        """
        Define transects along which land must be present (e.g. to block ocean
        flow). This method can be overridden in subclasses to either add
        additional transects or to replace the transects defined in the base
        class. Use the ``merge()`` method to add transects to the feature
        collection.

        Parameters
        ----------
        gf : geometric_features.GeometricFeatures
            The geometric features from which to get the transects

        Returns
        -------
        fc_crit_land_transects : geometric_features.FeatureCollection
            The transects that must be land
        """
        config = self.config
        section = config['cull_mesh']
        include_critical_transects = section.getboolean(
            'include_critical_transects'
        )
        if include_critical_transects:
            fc_crit_land_transects = gf.read(
                componentName='ocean',
                objectType='transect',
                tags=['Critical_Land_Blockage'],
            )
        else:
            fc_crit_land_transects = None

        return fc_crit_land_transects

    def define_critical_ocean_transects(self, gf):
        """
        Define transects along which ocean must be present (e.g. to allow ocean
        flow). This method can be overridden in subclasses to either add
        additional transects or to replace the transects defined in the base
        class. Use the ``merge()`` method to add transects to the feature
        collection.

        Parameters
        ----------
        gf : geometric_features.GeometricFeatures
            The geometric features from which to get the transects

        Returns
        -------
        fc_crit_ocean_transects : geometric_features.FeatureCollection
            The transects that must be ocean
        """
        config = self.config
        section = config['cull_mesh']
        include_critical_transects = section.getboolean(
            'include_critical_transects'
        )
        if include_critical_transects:
            fc_crit_ocean_transects = gf.read(
                componentName='ocean',
                objectType='transect',
                tags=['Critical_Passage'],
            )
        else:
            fc_crit_ocean_transects = None

        return fc_crit_ocean_transects

    def refine_ocean_cull_mask(self, ds_base_mesh, ds_topo, cull_mask):
        """
        Refine the mask for culling land and (optionally) grounded ice from
        the ocean. Subclasses can override this method to first refine the
        mask and then call the base class method to handle critical transects
        and land-locked cells.

        Parameters
        ----------
        ds_base_mesh : xarray.Dataset
            The dataset containing the base mesh

        ds_topo : xarray.Dataset
            The dataset containing the unsmoothed topography

        cull_mask : xarray.DataArray
            The current cull mask to refine

        Returns
        -------
        cull_mask : xarray.DataArray
            The refined cull mask
        """
        logger = self.logger
        config = self.config
        section = config['cull_mesh']
        latitude_threshold = section.getfloat('sea_ice_latitude_threshold')
        iterations = section.getint('land_locked_cell_iterations')

        # critical land transects must be culled from ocean
        crit_land_filename = 'critical_land_transects_mask.nc'
        if os.path.exists(crit_land_filename):
            logger.info(
                'Applying critical land transect mask to ocean cull mask.'
            )
            ds_crit = xr.open_dataset(crit_land_filename)
            preserve_land = ds_crit.regionCellMasks.isel(nRegions=0) > 0
            cull_mask = np.logical_or(cull_mask, preserve_land)

        # critical ocean transects must not be culled from ocean
        crit_ocean_filename = 'critical_ocean_transects_mask.nc'
        if os.path.exists(crit_ocean_filename):
            logger.info(
                'Applying critical ocean transect mask to ocean cull mask.'
            )
            ds_crit = xr.open_dataset(crit_ocean_filename)
            preserve_ocean = ds_crit.regionCellMasks.isel(nRegions=0) > 0
            cull_mask = np.logical_and(
                cull_mask, np.logical_not(preserve_ocean)
            )

        region_cell_mask = xr.where(cull_mask, 1, 0).expand_dims(
            dim='nRegions', axis=1
        )
        ds_mask = xr.Dataset()
        # make a copy so we can modify `regionCellMasks`
        ds_mask['regionCellMasks'] = region_cell_mask.copy()
        write_netcdf(ds_mask, 'ocean_cull_mask_with_critical_transects.nc')
        logger.info('Wrote ocean_cull_mask_with_critical_transects.nc.')

        ds_mask = add_land_locked_cells_to_mask(
            ds_mask,
            ds_base_mesh,
            latitude_threshold=latitude_threshold,
            nSweeps=iterations,
        )
        write_netcdf(ds_mask, 'ocean_cull_mask_with_land_locked_cells.nc')
        logger.info('Wrote ocean_cull_mask_with_land_locked_cells.nc.')

        ocean_mask = 1 - ds_mask.regionCellMasks.isel(nRegions=0)

        gf = GeometricFeatures()
        fc_seed = gf.read(
            componentName='ocean', objectType='point', tags=['seed_point']
        )
        # create a mask for the flood fill seed points
        ds_seed_mask = compute_mpas_flood_fill_mask(
            dsMesh=ds_base_mesh,
            daGrow=ocean_mask,
            fcSeed=fc_seed,
            logger=logger,
        )

        cull_mask = 1 - ds_seed_mask.cellSeedMask
        return cull_mask

    def refine_land_cull_mask(self, ds_base_mesh, ds_topo, cull_mask):
        """
        Refine the mask for culling ocean from the land. Subclasses can
        override this method to first refine the mask and then call the base
        class method to make sure that 1) ocean critical transects are excluded
        from the land and 2) all cells that are not part of the ocean (without
        ice-shelf cavities) are excluded from the land cull mask (someone
        is supposed to own every cell on the globe).

        Parameters
        ----------
        ds_base_mesh : xarray.Dataset
            The dataset containing the base mesh

        ds_topo : xarray.Dataset
            The dataset containing the unsmoothed topography

        cull_mask : xarray.DataArray
            The current cull mask to refine

        Returns
        -------
        cull_mask : xarray.DataArray
            The refined cull mask
        """
        logger = self.logger

        # the land cull mask must include the ocean critical transects and
        # exclude anything that was added to the ocean without cavities
        # during the flood fill, etc. in _create_ocean_no_cavities_cull_mask()

        # critical ocean transects must be culled from land
        crit_ocean_filename = 'critical_ocean_transects_mask.nc'
        if os.path.exists(crit_ocean_filename):
            logger.info(
                'Applying critical ocean transect mask to land cull mask.'
            )
            ds_crit = xr.open_dataset(crit_ocean_filename)
            preserve_ocean = ds_crit.regionCellMasks.isel(nRegions=0) > 0
            cull_mask = np.logical_or(cull_mask, preserve_ocean)

        ds_ocean_no_cavity_cull_mask = xr.open_dataset(
            'ocean_no_cavities_cull_mask.nc'
        )

        ocean_no_cavity_mask = (
            ds_ocean_no_cavity_cull_mask.oceanNoCavitiesCullMask == 0
        )

        # only cull cells from the land if they are not going to be culled
        # from the ocean (without cavities).  Someone is supposed to own
        # every cell on the globe.
        cull_mask = np.logical_and(cull_mask, ocean_no_cavity_mask)

        cull_mask = xr.where(cull_mask, 1, 0)
        return cull_mask

    def run(self):
        """
        Run this step of the test case
        """
        super().run()
        logger = self.logger
        logger.info('Starting CullMaskStep run sequence.')
        self._create_critical_transects()
        self._create_ocean_cull_mask()
        self._create_land_ice_mask()
        self._create_ocean_no_cavities_cull_mask()
        self._create_land_cull_mask()
        self._combine_masks()
        logger.info('Completed CullMaskStep run sequence.')

    def _create_critical_transects(self):
        """
        Create masks for the critical transects that must be land or ocean
        """
        logger = self.logger
        logger.info('Creating critical transect masks.')
        config = self.config
        section = config['cull_mesh']
        latitude_threshold = section.getfloat('sea_ice_latitude_threshold')

        cpus_per_task = self.cpus_per_task
        netcdf_format = mpas_tools.io.default_format
        netcdf_engine = mpas_tools.io.default_engine

        gf = GeometricFeatures()
        gf.read(
            componentName='ocean',
            objectType='transect',
            tags=['Critical_Land_Blockage', 'Critical_Passage'],
        )

        ds_base_mesh = xr.open_dataset('base_mesh.nc')

        fc_crit_land_transects = self.define_critical_land_transects(gf)

        if fc_crit_land_transects is not None:
            logger.info('Processing critical land transects.')
            geojson_filename = 'critical_land_transects.geojson'
            nc_filename = 'critical_land_transects_all.nc'
            fc_crit_land_transects.to_geojson(geojson_filename)
            args = [
                'compute_mpas_transect_masks',
                '-m',
                'base_mesh.nc',
                '-g',
                geojson_filename,
                '-o',
                nc_filename,
                '-t',
                'cell',
                '-s',
                '10e3',
                '--process_count',
                f'{cpus_per_task}',
                '--format',
                netcdf_format,
                '--engine',
                netcdf_engine,
            ]
            check_call(args, logger=logger)

            ds_all = xr.open_dataset(nc_filename)

            # combine into a single field
            preserve = xr.where(
                ds_all.transectCellMasks.sum(dim='nTransects') > 0, 1, 0
            )

            ds_mask = xr.Dataset()
            ds_mask['regionCellMasks'] = preserve
            ds_mask['regionCellMasks'] = ds_mask.regionCellMasks.expand_dims(
                dim='nRegions', axis=1
            )

            write_netcdf(ds_mask, 'critical_land_transects_mask.nc')
            logger.info('Wrote critical_land_transects_mask.nc.')

        fc_crit_ocean_transects = self.define_critical_ocean_transects(gf)

        if fc_crit_ocean_transects is not None:
            logger.info('Processing critical ocean transects.')
            geojson_filename = 'critical_ocean_transects.geojson'
            nc_filename = 'critical_ocean_transects_all.nc'
            fc_crit_ocean_transects.to_geojson(geojson_filename)
            args = [
                'compute_mpas_transect_masks',
                '-m',
                'base_mesh.nc',
                '-g',
                geojson_filename,
                '-o',
                nc_filename,
                '-t',
                'cell',
                'edge',
                '-s',
                '10e3',
                '--process_count',
                f'{cpus_per_task}',
                '--format',
                netcdf_format,
                '--engine',
                netcdf_engine,
            ]
            check_call(args, logger=logger)
            ds_all = xr.open_dataset(nc_filename)

            ds_widened = widen_transect_edge_masks(
                ds_all, ds_base_mesh, latitude_threshold=latitude_threshold
            )
            write_netcdf(ds_widened, 'critical_ocean_transects_widened.nc')
            logger.info('Wrote critical_ocean_transects_widened.nc.')

            # combine into a single field
            preserve = xr.where(
                ds_widened.transectCellMasks.sum(dim='nTransects') > 0, 1, 0
            )

            ds_mask = xr.Dataset()
            ds_mask['regionCellMasks'] = preserve
            ds_mask['regionCellMasks'] = ds_mask.regionCellMasks.expand_dims(
                dim='nRegions', axis=1
            )

            write_netcdf(ds_mask, 'critical_ocean_transects_mask.nc')
            logger.info('Wrote critical_ocean_transects_mask.nc.')

    def _create_ocean_cull_mask(self):
        """
        Create a mask for culling land and grounded land ice from the ocean
        such that the ocean is contiguous, excludes critical land transects,
        includes critical ocean transects and accounts for land-locked.
        """
        logger = self.logger
        logger.info('Creating ocean cull mask.')

        ds_base_mesh = xr.open_dataset('base_mesh.nc')

        ds_topo = xr.open_dataset('topography_unsmoothed.nc')
        ocean_frac = ds_topo.ocean_frac
        cull_mask = ocean_frac < 0.5

        cull_mask = self.refine_ocean_cull_mask(
            ds_base_mesh=ds_base_mesh,
            ds_topo=ds_topo,
            cull_mask=cull_mask,
        )

        ds_mask = xr.Dataset()
        ds_mask['oceanCullMask'] = cull_mask

        write_netcdf(ds_mask, 'ocean_cull_mask.nc')
        logger.info('Wrote ocean_cull_mask.nc.')

    def _create_land_ice_mask(self):
        """
        Create a mask for Antarctic land ice
        """
        logger = self.logger
        logger.info('Creating Antarctic land ice mask.')
        config = self.config
        section = config['cull_mesh']
        land_ice_max_latitude = section.getfloat('land_ice_max_latitude')
        land_ice_min_fraction = section.getfloat('land_ice_min_fraction')

        ds_base_mesh = xr.open_dataset('base_mesh.nc')

        ds_topo = xr.open_dataset('topography_unsmoothed.nc')
        land_ice_frac = ds_topo.ice_frac
        land_ice_present = land_ice_frac > land_ice_min_fraction

        ds_ocean_cull_mask = xr.open_dataset('ocean_cull_mask.nc')
        ocean_cull_mask = ds_ocean_cull_mask.oceanCullMask > 0

        lat_cell = np.degrees(ds_base_mesh.latCell)
        antarctic_not_ocean = np.logical_and(
            ocean_cull_mask > 0, lat_cell < land_ice_max_latitude
        )

        # include areas we're culling from the ocean that are south of
        # land_ice_max_latitude -- if it's not ocean, it's land ice.  This
        # should also take care of critical transects
        land_ice_present = np.logical_or(land_ice_present, antarctic_not_ocean)

        # flood fill the land ice mask from the south pole
        logger.info('Flood filling land ice mask from south pole.')
        fc_south_pole_seed = read_feature_collection('south_pole.geojson')

        ds_mask = compute_mpas_flood_fill_mask(
            dsMesh=ds_base_mesh,
            daGrow=xr.where(land_ice_present, 1, 0),
            fcSeed=fc_south_pole_seed,
            logger=self.logger,
        )
        land_ice_present = ds_mask.cellSeedMask

        land_ice_frac = land_ice_frac.where(land_ice_present, 0.0)
        land_ice_mask = xr.where(land_ice_frac > 0.5, 1, 0)

        # write the land ice mask to a file
        ds_mask = xr.Dataset()
        ds_mask['landIceMask'] = land_ice_mask
        write_netcdf(ds_mask, 'land_ice_mask_preliminary.nc')
        logger.info('Wrote land_ice_mask_preliminary.nc.')

    def _create_ocean_no_cavities_cull_mask(self):
        """
        Create a mask for culling land and all land ice (both grounded and
        floating) from the ocean such that the ocean is contiguous, excludes
        critical land transects, includes critical ocean transects and accounts
        for land-locked.  Update the land-ice mask to include any areas that
        will be removed from the open ocean by these updates.
        """
        logger = self.logger
        logger.info('Creating ocean no-cavities cull mask.')
        config = self.config
        section = config['cull_mesh']
        latitude_threshold = section.getfloat('sea_ice_latitude_threshold')
        iterations = section.getint('land_locked_cell_iterations')

        ds_base_mesh = xr.open_dataset('base_mesh.nc')

        ds_ocean_cull_mask = xr.open_dataset('ocean_cull_mask.nc')
        ocean_cull_mask = ds_ocean_cull_mask.oceanCullMask > 0

        ds_land_ice_mask = xr.open_dataset('land_ice_mask_preliminary.nc')
        land_ice_mask = ds_land_ice_mask.landIceMask > 0

        # Exclude all land ice, not just the grounded ice
        cull_mask = np.logical_or(ocean_cull_mask, land_ice_mask)
        cull_mask_orig = cull_mask.copy()

        region_cell_mask = xr.where(cull_mask, 1, 0).expand_dims(
            dim='nRegions', axis=1
        )
        ds_mask = xr.Dataset()
        # make a copy so we can modify `regionCellMasks`
        ds_mask['regionCellMasks'] = region_cell_mask.copy()

        ds_mask = add_land_locked_cells_to_mask(
            ds_mask,
            ds_base_mesh,
            latitude_threshold=latitude_threshold,
            nSweeps=iterations,
        )

        cull_mask = ds_mask.regionCellMasks.isel(nRegions=0)

        gf = GeometricFeatures()
        fc_ocean_seed = gf.read(
            componentName='ocean', objectType='point', tags=['seed_point']
        )

        logger.info('Flood filling ocean no-cavities mask from seed points.')
        ds_mask = compute_mpas_flood_fill_mask(
            dsMesh=ds_base_mesh,
            daGrow=xr.where(cull_mask, 0, 1),
            fcSeed=fc_ocean_seed,
            logger=self.logger,
        )

        cull_mask = xr.where(ds_mask.cellSeedMask > 0, 0, 1)

        cull_mask_added = np.logical_and(
            cull_mask,
            np.logical_not(cull_mask_orig),
        )
        land_ice_mask = np.logical_or(
            land_ice_mask,
            cull_mask_added,
        )

        ds_mask = xr.Dataset()
        ds_mask['oceanNoCavitiesCullMask'] = cull_mask
        write_netcdf(ds_mask, 'ocean_no_cavities_cull_mask.nc')
        logger.info('Wrote ocean_no_cavities_cull_mask.nc.')

        ds_mask = xr.Dataset()
        ds_mask['landIceMask'] = land_ice_mask
        write_netcdf(ds_mask, 'land_ice_mask.nc')
        logger.info('Wrote land_ice_mask.nc.')

    def _create_land_cull_mask(self):
        """
        Create a mask for culling ocean from the land such that makes sure to
        include all cells that are not in the ocean without ice-shelf cavities
        and excludes critical ocean transects
        """
        logger = self.logger
        logger.info('Creating land cull mask.')

        ds_topo = xr.open_dataset('topography_unsmoothed.nc')
        land_frac = ds_topo.land_frac
        cull_mask = land_frac < 0.5

        cull_mask = self.refine_land_cull_mask(
            ds_base_mesh=xr.open_dataset('base_mesh.nc'),
            ds_topo=ds_topo,
            cull_mask=cull_mask,
        )

        ds_mask = xr.Dataset()
        ds_mask['landCullMask'] = cull_mask
        write_netcdf(ds_mask, 'land_cull_mask.nc')
        logger.info('Wrote land_cull_mask.nc.')

    def _combine_masks(self):
        """
        Combine the land and ocean (with and without cavities) cull masks as
        well as the land-ice mask into a single file
        """
        logger = self.logger
        logger.info('Combining land and ocean cull masks.')

        ds_ocean_cull_mask = xr.open_dataset('ocean_cull_mask.nc')
        ds_ocean_no_cavities_cull_mask = xr.open_dataset(
            'ocean_no_cavities_cull_mask.nc'
        )
        ds_land_cull_mask = xr.open_dataset('land_cull_mask.nc')
        ds_land_ice_mask = xr.open_dataset('land_ice_mask.nc')

        ds_masks = xr.Dataset()
        ds_masks['oceanCullMask'] = ds_ocean_cull_mask.oceanCullMask
        ds_masks['oceanNoCavitiesCullMask'] = (
            ds_ocean_no_cavities_cull_mask.oceanNoCavitiesCullMask
        )
        ds_masks['landCullMask'] = ds_land_cull_mask.landCullMask
        ds_masks['landIceMask'] = ds_land_ice_mask.landIceMask

        write_netcdf(ds_masks, 'cull_masks.nc')
        logger.info('Wrote cull_masks.nc.')
