import os

import mpas_tools.io
import numpy as np
import xarray as xr
from geometric_features import (
    GeometricFeatures,
    read_feature_collection,
)
from mpas_tools.io import open_dataset, write_netcdf
from mpas_tools.logging import check_call
from mpas_tools.mesh.mask import compute_mpas_flood_fill_mask
from mpas_tools.ocean.coastline_alteration import widen_transect_edge_masks

from polaris import Step
from polaris.mesh.connectivity import seed_mask_from_points
from polaris.mesh.spherical.critical_transects import (
    load_default_critical_transects,
)
from polaris.tasks.e3sm.init.topo.cull.consistency import (
    check_critical_passages,
    check_cull_mask_consistency,
    check_land_locked_criteria,
)
from polaris.tasks.e3sm.init.topo.cull.dc_edge_diagnostics import (
    check_ocean_dc_edge,
)
from polaris.tasks.e3sm.init.topo.cull.land_locked import (
    remove_land_locked_cells,
    remove_ocean_land_locked_cells,
)


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

    sizing_field_step : polaris.Step or None
        For unified meshes, the sizing-field build step whose
        ``sizing_field.nc`` provides the ocean background cell width used
        by the ``dcEdge`` diagnostic
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        unsmoothed_topo_step,
        name,
        subdir,
        sizing_field_step=None,
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

        sizing_field_step : polaris.Step, optional
            For unified meshes, the sizing-field build step whose
            ``sizing_field.nc`` provides the ocean background cell width
            used by the ``dcEdge`` diagnostic
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
        self.sizing_field_step = sizing_field_step

        self.add_input_file(
            filename='south_pole.geojson',
            package='polaris.tasks.e3sm.init.topo.cull.mask',
        )

        self.add_output_file(filename='cull_masks.nc')
        self._critical_transects = None

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

        if self.sizing_field_step is not None:
            self.add_input_file(
                filename='sizing_field.nc',
                work_dir_target=os.path.join(
                    self.sizing_field_step.path,
                    self.sizing_field_step.sizing_field_filename,
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
            fc_crit_land_transects = self._load_default_critical_transects(
                gf
            ).land_blockages
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
            fc_crit_ocean_transects = self._load_default_critical_transects(
                gf
            ).passages
        else:
            fc_crit_ocean_transects = None

        return fc_crit_ocean_transects

    def _load_default_critical_transects(self, gf):
        """
        Load and cache the shared default critical transects.

        Parameters
        ----------
        gf : geometric_features.GeometricFeatures
            The geometric features from which to get the transects

        Returns
        -------
        polaris.mesh.spherical.critical_transects.CriticalTransects
            The shared critical transects
        """
        if self._critical_transects is None:
            self._critical_transects = load_default_critical_transects(gf)
        return self._critical_transects

    def refine_ocean_cull_mask(self, ds_base_mesh, ds_topo, cull_mask):
        """
        Refine the mask for culling land and (optionally) grounded ice from
        the ocean. Subclasses can override this method to first refine the
        mask and then call the base class method to handle critical transects
        and land-locked cells.

        The base class applies the critical transects, removes the cells with
        fewer than two active edges, through which a C-grid cannot
        circulate, and discards whatever is left unconnected to the open
        ocean. The sea-ice criteria are not applied here; they belong to the
        ocean without ice-shelf cavities and are applied when the two domains
        are refined together. See the ``land_locked_cells`` design document.

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

        cull_mask = self._apply_critical_transects(
            cull_mask=cull_mask,
            mask_name='ocean cull mask',
        )

        logger.info('Removing land-locked cells from the ocean.')
        ocean_mask = remove_ocean_land_locked_cells(
            ds_mesh=ds_base_mesh,
            ocean_mask=np.logical_not(cull_mask),
            ocean_seed_mask=self._ocean_seed_mask(ds_base_mesh),
        )

        return xr.DataArray(np.logical_not(ocean_mask), dims=('nCells',))

    def refine_land_cull_mask(self, ds_base_mesh, ds_topo, cull_mask):
        """
        Refine the mask for culling ocean from the land.  The mask passed in
        is already the complement of the ocean without ice-shelf cavities,
        which the base class returns unaltered: someone is supposed to own
        every cell on the globe and no one is supposed to own it twice.

        Subclasses can override this method to define a different land
        domain, but one that breaks the complementarity must also override
        :py:meth:`CullMaskStep._check_mask_consistency`, which would
        otherwise reject the resulting masks.

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
        self._refine_ocean_domains()
        self._check_critical_passages()
        self._create_land_cull_mask()
        self._combine_masks()
        self._check_mask_consistency()
        self._check_ocean_dc_edge()
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

        ds_base_mesh = open_dataset('base_mesh.nc')

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

            ds_all = open_dataset(nc_filename)

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
            ds_all = open_dataset(nc_filename)

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

    def _apply_critical_transects(
        self, cull_mask, mask_name, ocean_cull_mask=None
    ):
        """
        Apply the critical land blockages and the critical ocean passages to
        an ocean cull mask.  Cells along critical land transects must be
        culled from the ocean and cells along critical ocean transects must
        not be.  The same treatment is applied to the ocean with and without
        ice-shelf cavities, so that a passage that keeps a cell in the ocean
        also keeps it in the ocean without cavities.

        Parameters
        ----------
        cull_mask : xarray.DataArray
            The cull mask to update

        mask_name : str
            The name of the mask being updated, used in log messages

        ocean_cull_mask : xarray.DataArray, optional
            The cull mask for the ocean including ice-shelf cavities.  If
            given, critical ocean transects are preserved only at cells that
            the ocean itself retains, so the resulting domain cannot contain
            cells that are absent from the ocean.

        Returns
        -------
        cull_mask : xarray.DataArray
            The updated cull mask
        """
        logger = self.logger

        # critical land transects must be culled from the ocean
        crit_land_filename = 'critical_land_transects_mask.nc'
        if os.path.exists(crit_land_filename):
            logger.info(
                f'Applying critical land transect mask to {mask_name}.'
            )
            ds_crit = open_dataset(crit_land_filename)
            preserve_land = ds_crit.regionCellMasks.isel(nRegions=0) > 0
            cull_mask = np.logical_or(cull_mask, preserve_land)

        # critical ocean transects must not be culled from the ocean
        crit_ocean_filename = 'critical_ocean_transects_mask.nc'
        if os.path.exists(crit_ocean_filename):
            logger.info(
                f'Applying critical ocean transect mask to {mask_name}.'
            )
            ds_crit = open_dataset(crit_ocean_filename)
            preserve_ocean = ds_crit.regionCellMasks.isel(nRegions=0) > 0
            if ocean_cull_mask is not None:
                # a critical ocean transect cell that the ocean does not
                # retain must not be added back here
                preserve_ocean = np.logical_and(
                    preserve_ocean, np.logical_not(ocean_cull_mask)
                )
            cull_mask = np.logical_and(
                cull_mask, np.logical_not(preserve_ocean)
            )

        return cull_mask

    def _create_ocean_cull_mask(self):
        """
        Create a mask for culling land and grounded land ice from the ocean
        such that the ocean is contiguous, excludes critical land transects,
        includes critical ocean transects and accounts for land-locked.
        """
        logger = self.logger
        logger.info('Creating ocean cull mask.')

        ds_base_mesh = open_dataset('base_mesh.nc')

        ds_topo = open_dataset('topography_unsmoothed.nc')
        ocean_frac = ds_topo.ocean_frac
        cull_mask = ocean_frac < 0.5

        cull_mask = self.refine_ocean_cull_mask(
            ds_base_mesh=ds_base_mesh,
            ds_topo=ds_topo,
            cull_mask=cull_mask,
        )

        ds_mask = xr.Dataset()
        ds_mask['oceanCullMask'] = cull_mask

        write_netcdf(ds_mask, 'ocean_cull_mask_preliminary.nc')
        logger.info('Wrote ocean_cull_mask_preliminary.nc.')

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

        ds_base_mesh = open_dataset('base_mesh.nc')

        ds_topo = open_dataset('topography_unsmoothed.nc')
        land_ice_frac = ds_topo.ice_frac

        ds_ocean_cull_mask = open_dataset('ocean_cull_mask_preliminary.nc')
        ocean_cull_mask = ds_ocean_cull_mask.oceanCullMask > 0

        land_ice_present = self._antarctic_land_ice_ownership(
            ds_topo=ds_topo,
            ocean_cull_mask=ocean_cull_mask,
            lat_cell=np.degrees(ds_base_mesh.latCell),
            land_ice_max_latitude=land_ice_max_latitude,
            land_ice_min_fraction=land_ice_min_fraction,
        )

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

    def _refine_ocean_domains(self):
        """
        Refine the ocean and the ocean without ice-shelf cavities together,
        removing the cells through which the ocean cannot circulate and
        those in which sea ice would be trapped, and write the final cull
        masks and land-ice mask.

        The two domains are refined together because removing a cell from
        one can strand a cell in the other, and because only here is the
        land-ice mask available to say which cells may legitimately be in
        the ocean but not in the ocean without cavities.  See the
        ``land_locked_cells`` design document.
        """
        logger = self.logger
        logger.info('Refining the ocean and ocean no-cavities domains.')
        config = self.config
        section = config['cull_mesh']
        latitude_threshold = section.getfloat('sea_ice_latitude_threshold')

        ds_base_mesh = open_dataset('base_mesh.nc')

        ds_preliminary = open_dataset('ocean_cull_mask_preliminary.nc')
        ocean_cull_mask = ds_preliminary.oceanCullMask > 0

        ds_land_ice_mask = open_dataset('land_ice_mask_preliminary.nc')
        land_ice_mask = ds_land_ice_mask.landIceMask > 0

        # exclude all land ice, not just the grounded ice
        cull_mask = np.logical_or(ocean_cull_mask, land_ice_mask)

        # excluding the land ice can undo the critical transects that were
        # applied to the ocean cull mask, so they have to be applied again
        cull_mask = self._apply_critical_transects(
            cull_mask=cull_mask,
            mask_name='ocean no-cavities cull mask',
            ocean_cull_mask=ocean_cull_mask,
        )

        ocean, no_cavities = remove_land_locked_cells(
            ds_mesh=ds_base_mesh,
            ocean_mask=np.logical_not(ocean_cull_mask).values,
            no_cavities_mask=np.logical_not(cull_mask).values,
            land_ice_mask=land_ice_mask.values,
            ocean_seed_mask=self._ocean_seed_mask(ds_base_mesh),
            latitude_threshold=latitude_threshold,
            logger=logger,
        )

        # critical transects outrank the ice masks: a cell that a critical
        # ocean transect keeps in the ocean without cavities is open water,
        # not an ice-shelf cavity.  This makes the cavity cells of the ocean
        # mesh exactly those cells the ocean retains and the ocean without
        # cavities does not.
        land_ice = np.logical_and(land_ice_mask.values, ~no_cavities)

        ds_mask = xr.Dataset()
        ds_mask['oceanCullMask'] = _cull_mask_array(ocean)
        write_netcdf(ds_mask, 'ocean_cull_mask.nc')
        logger.info('Wrote ocean_cull_mask.nc.')

        ds_mask = xr.Dataset()
        ds_mask['oceanNoCavitiesCullMask'] = _cull_mask_array(no_cavities)
        write_netcdf(ds_mask, 'ocean_no_cavities_cull_mask.nc')
        logger.info('Wrote ocean_no_cavities_cull_mask.nc.')

        ds_mask = xr.Dataset()
        ds_mask['landIceMask'] = xr.DataArray(
            np.where(land_ice, 1, 0), dims=('nCells',)
        )
        write_netcdf(ds_mask, 'land_ice_mask.nc')
        logger.info('Wrote land_ice_mask.nc.')

    def _create_land_cull_mask(self):
        """
        Create a mask for culling ocean from the land.  The land domain is the
        complement of the ocean without ice-shelf cavities, so that every cell
        on the globe is owned by exactly one of the two.
        """
        logger = self.logger
        logger.info('Creating land cull mask.')

        ds_ocean_no_cavities = open_dataset('ocean_no_cavities_cull_mask.nc')

        # cull from the land exactly the cells that the ocean without
        # ice-shelf cavities retains.  A land-fraction test of its own is not
        # needed and would not be consistent: the ocean without cavities has
        # already been through the critical transects, the land-locked-cell
        # check and the flood fill.
        cull_mask = ds_ocean_no_cavities.oceanNoCavitiesCullMask == 0

        cull_mask = self.refine_land_cull_mask(
            ds_base_mesh=open_dataset('base_mesh.nc'),
            ds_topo=open_dataset('topography_unsmoothed.nc'),
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

        ds_ocean_cull_mask = open_dataset('ocean_cull_mask.nc')
        ds_ocean_no_cavities_cull_mask = open_dataset(
            'ocean_no_cavities_cull_mask.nc'
        )
        ds_land_cull_mask = open_dataset('land_cull_mask.nc')
        ds_land_ice_mask = open_dataset('land_ice_mask.nc')

        ds_masks = xr.Dataset()
        ds_masks['oceanCullMask'] = ds_ocean_cull_mask.oceanCullMask
        ds_masks['oceanNoCavitiesCullMask'] = (
            ds_ocean_no_cavities_cull_mask.oceanNoCavitiesCullMask
        )
        ds_masks['landCullMask'] = ds_land_cull_mask.landCullMask
        ds_masks['landIceMask'] = ds_land_ice_mask.landIceMask

        write_netcdf(ds_masks, 'cull_masks.nc')
        logger.info('Wrote cull_masks.nc.')

    def _check_critical_passages(self):
        """
        Check that removing land-locked cells did not close any critical
        ocean passage.
        """
        logger = self.logger
        filename = 'critical_ocean_transects_widened.nc'
        if not os.path.exists(filename):
            logger.info(
                'No critical ocean transects, skipping the passage check.'
            )
            return

        ds_masks = open_dataset('ocean_cull_mask.nc')
        check_critical_passages(
            ocean_cull_mask=ds_masks.oceanCullMask.values,
            ds_transects=open_dataset(filename),
            logger=logger,
        )

    def _check_mask_consistency(self):
        """
        Check that the ocean, ocean without ice-shelf cavities, land and
        land-ice masks describe consistent domains.
        """
        config = self.config
        convention = config.get(
            'spherical_mesh', 'antarctic_boundary_convention'
        )

        ds_masks = open_dataset('cull_masks.nc')

        check_land_locked_criteria(
            ds_mesh=open_dataset('base_mesh.nc'),
            ocean_cull_mask=ds_masks.oceanCullMask.values,
            ocean_no_cavities_cull_mask=(
                ds_masks.oceanNoCavitiesCullMask.values
            ),
            latitude_threshold=config.getfloat(
                'cull_mesh', 'sea_ice_latitude_threshold'
            ),
            logger=self.logger,
        )

        check_cull_mask_consistency(
            ocean_cull_mask=ds_masks.oceanCullMask.values,
            ocean_no_cavities_cull_mask=(
                ds_masks.oceanNoCavitiesCullMask.values
            ),
            land_cull_mask=ds_masks.landCullMask.values,
            land_ice_mask=ds_masks.landIceMask.values,
            convention=convention,
            logger=self.logger,
        )

    def _check_ocean_dc_edge(self):
        """
        Check that dcEdge in the ocean/sea-ice domain stays within
        bounds relative to the local ocean background cell width (only
        available for unified meshes with a sizing-field step).
        """
        logger = self.logger
        if self.sizing_field_step is None:
            logger.info(
                'No sizing-field step, skipping the dcEdge diagnostic.'
            )
            return

        config = self.config
        section = config['cull_mesh']
        min_ratio = section.getfloat('min_dc_edge_ratio')
        max_ratio = section.getfloat('max_dc_edge_ratio')

        ds_base_mesh = open_dataset('base_mesh.nc')
        ds_masks = open_dataset('cull_masks.nc')
        ds_sizing = open_dataset('sizing_field.nc')

        check_ocean_dc_edge(
            ds_base_mesh=ds_base_mesh,
            ocean_cull_mask=ds_masks.oceanCullMask.values,
            ds_sizing=ds_sizing,
            min_ratio=min_ratio,
            max_ratio=max_ratio,
            logger=logger,
        )

    @staticmethod
    def _ocean_seed_mask(ds_base_mesh):
        """
        Find the base-mesh cells nearest the ocean seed points, used to
        seed the flood fill that keeps the ocean contiguous.
        """
        gf = GeometricFeatures()
        fc_seed = gf.read(
            componentName='ocean', objectType='point', tags=['seed_point']
        )
        points = np.array(
            [
                feature['geometry']['coordinates']
                for feature in fc_seed.features
            ]
        )
        return seed_mask_from_points(ds_base_mesh, points[:, 0], points[:, 1])

    @staticmethod
    def _antarctic_land_ice_ownership(
        ds_topo,
        ocean_cull_mask,
        lat_cell,
        land_ice_max_latitude,
        land_ice_min_fraction,
    ):
        """
        Determine Antarctic cells that should be owned by land ice.
        """
        land_ice_present = ds_topo.ice_frac > land_ice_min_fraction
        antarctic_not_ocean = np.logical_and(
            ocean_cull_mask, lat_cell < land_ice_max_latitude
        )
        return np.logical_or(land_ice_present, antarctic_not_ocean)


def _cull_mask_array(keep_mask):
    """
    Convert a boolean mask of cells to keep into a cull mask, which is 1
    where cells are culled away and 0 where they are kept.
    """
    return xr.DataArray(np.where(keep_mask, 0, 1), dims=('nCells',))
