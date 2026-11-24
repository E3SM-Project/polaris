import os
import pathlib

import numpy as np
import pyproj
import xarray as xr
from mpas_tools.logging import check_call
from pyremap import ProjectionGridDescriptor, get_lat_lon_descriptor

from polaris.archive import extract_zip_member
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.files import (
    DATASETS,
    GLOBAL,
    get_combine_files,
    write_netcdf_with_fill_values,
)


def interp_firn_air_content(filename, x, y):
    """
    Interpolate the firn air content of a BedMachine Antarctica dataset
    bilinearly to another grid in the same projection

    Parameters
    ----------
    filename : str
        The BedMachine Antarctica file, with ``firn`` on its ``x`` and ``y``
        coordinates

    x : xarray.DataArray
        The x coordinate (m) of the grid to interpolate to

    y : xarray.DataArray
        The y coordinate (m) of the grid to interpolate to

    Returns
    -------
    firn : xarray.DataArray
        The firn air content (m) on the grid, zero where it is missing and
        outside the BedMachine grid
    """
    ds = xr.open_dataset(filename)
    firn = ds.firn.fillna(0.0)
    # the coordinates are 1D, so xarray interpolates along x, then along y
    firn = firn.interp(x=x, y=y, method='linear')
    return firn.fillna(0.0)


class PrepareCombineStep(Step):
    """
    A step for getting the global and Antarctic topography datasets ready to
    be remapped to the target grid of combined topography.  It adds the
    fields MPAS-Ocean needs, splits the global dataset into tiles and makes
    SCRIP files for the Antarctic dataset and the target grid.
    """

    def __init__(self, component, subdir, name):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory within the component's work directory

        name : str
            The name of the step
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )

    def setup(self):
        """
        Set up the step in the work directory, including downloading the
        datasets
        """
        super().setup()
        files = get_combine_files(self.config)

        datasets = [files.antarctic, GLOBAL]
        firn_dataset = DATASETS[files.antarctic].get('firn_dataset')
        if firn_dataset is not None:
            datasets.append(firn_dataset)
        for dataset in datasets:
            info = DATASETS[dataset]
            source = info.get('source_filename', info['filename'])
            self.add_input_file(
                filename=source,
                target=source,
                database='topo',
                url=info.get('url'),
            )

        self.add_output_file(filename=files.target_scrip)
        if files.exodus is not None:
            self.add_output_file(filename=files.exodus)
        self.add_output_file(filename=files.antarctic_modified)
        self.add_output_file(filename=files.antarctic_scrip)
        for tile in files.tiles:
            self.add_output_file(filename=tile.source)

    def run(self):
        """
        Run this step
        """
        files = get_combine_files(self.config)

        global_info = DATASETS[GLOBAL]
        if GLOBAL in ['gebco2023']:
            global_source = global_info['source_filename']
            archive_member = global_info['archive_member']
            self.logger.info(
                f'Extracting {archive_member} from {global_source}'
            )
            extract_zip_member(
                global_source, archive_member, files.global_extracted
            )
            self.logger.info('  Done.')
            self._modify_gebco(
                in_filename=files.global_extracted,
                out_filename=files.global_modified,
            )

        antarctic_info = DATASETS[files.antarctic]
        antarctic_source = antarctic_info.get(
            'source_filename', antarctic_info['filename']
        )
        if files.antarctic in ['bedmachinev3', 'bedmachinev4']:
            self._modify_bedmachine(
                in_filename=antarctic_source,
                out_filename=files.antarctic_modified,
            )
        elif files.antarctic in ['bedmap3']:
            firn_info = DATASETS[antarctic_info['firn_dataset']]
            self._modify_bedmap3(
                in_filename=antarctic_source,
                firn_filename=firn_info['filename'],
                out_filename=files.antarctic_modified,
            )

        self._create_target_scrip_file(files)
        self._create_global_tiles(files)
        self._create_antarctic_scrip_file(
            antarctic=files.antarctic,
            in_filename=files.antarctic_modified,
            scrip_filename=files.antarctic_scrip,
        )

    def _modify_gebco(self, in_filename, out_filename):
        """
        Modify GEBCO to include lon/lat bounds and an ocean mask
        """
        logger = self.logger
        logger.info('Adding bounds and an ocean mask to GEBCO')

        # Modify GEBCO
        gebco = xr.open_dataset(in_filename)
        lat = gebco.lat
        lon = gebco.lon
        dlat = lat.isel(lat=1) - lat.isel(lat=0)
        dlon = lon.isel(lon=1) - lon.isel(lon=0)
        lat_bnds = xr.concat([lat - 0.5 * dlat, lat + 0.5 * dlat], dim='bnds')
        lon_bnds = xr.concat([lon - 0.5 * dlon, lon + 0.5 * dlon], dim='bnds')
        gebco['lat_bnds'] = lat_bnds.transpose('lat', 'bnds')
        gebco['lon_bnds'] = lon_bnds.transpose('lon', 'bnds')
        gebco.lat.attrs['bounds'] = 'lat_bnds'
        gebco.lon.attrs['bounds'] = 'lon_bnds'
        gebco['ocean_mask'] = (gebco.elevation < 0.0).astype(float)

        # Write modified GEBCO to netCDF
        write_netcdf_with_fill_values(gebco, out_filename)
        logger.info('  Done.')

    def _modify_bedmachine(self, in_filename, out_filename):
        """
        Modify BedMachineAntarctica to compute the fields needed by MPAS-Ocean
        """
        logger = self.logger
        logger.info('Modifying BedMachineAntarctica with MPAS-Ocean names')

        # Load BedMachine and get ice, ocean and grounded masks
        bedmachine = xr.open_dataset(in_filename)
        mask = bedmachine.mask
        ice_mask = (mask != 0).astype(float)
        ocean_mask = np.logical_or(mask == 0, mask == 3).astype(float)
        grounded_mask = np.logical_or(
            np.logical_or(mask == 1, mask == 2), mask == 4
        ).astype(float)

        # Add new variables and apply ocean mask
        bedmachine['base_elevation'] = bedmachine.bed
        bedmachine['ice_thickness'] = bedmachine.thickness
        bedmachine['ice_draft'] = bedmachine.surface - bedmachine.thickness
        bedmachine.ice_draft.attrs['units'] = 'm'
        bedmachine['ice_mask'] = ice_mask
        bedmachine['grounded_mask'] = grounded_mask
        bedmachine['ocean_mask'] = ocean_mask
        bedmachine['valid_mask'] = xr.ones_like(ocean_mask)

        # Remove all other variables
        varlist = [
            'base_elevation',
            'ice_draft',
            'ice_thickness',
            'ice_mask',
            'grounded_mask',
            'ocean_mask',
            'valid_mask',
        ]
        bedmachine = bedmachine[varlist]

        # Write modified BedMachine to netCDF
        write_netcdf_with_fill_values(bedmachine, out_filename)
        logger.info('  Done.')

    def _modify_bedmap3(self, in_filename, firn_filename, out_filename):
        """
        Modify Bedmap3 to compute the fields needed by MPAS-Ocean.

        Bedmap3's thickness is the total thickness of the ice column,
        including the air in the firn.  The firn air content from
        ``firn_filename``, interpolated bilinearly to the Bedmap3 grid, is
        subtracted from it to give an ice-equivalent thickness like
        BedMachine's.  The ice draft comes from the total thickness.
        """
        logger = self.logger
        logger.info('Modifying Bedmap3 with MPAS-Ocean names')

        # Load Bedamp3 and get ice, ocean and grounded masks
        bedmap3 = xr.open_dataset(in_filename)
        mask = bedmap3.mask
        # -9999 = open ocean,
        # 1     = grounded ice,
        # 2     = transiently grounded ice shelf,
        # 3     = floating ice shelf,
        # 4     = rock
        ice_mask = (mask.notnull()).astype(float)
        ocean_mask = np.logical_or(mask.isnull(), mask == 3).astype(float)
        grounded_mask = np.logical_or(
            np.logical_or(mask == 1, mask == 2), mask == 4
        ).astype(float)

        # Add new variables and apply ocean mask
        bedmap3['base_elevation'] = bedmap3.bed_topography
        bedmap3['ice_draft'] = (
            bedmap3.surface_topography - bedmap3.ice_thickness
        )
        bedmap3.ice_draft.attrs['units'] = 'm'

        logger.info(f'  Subtracting firn air content from {firn_filename}')
        firn = interp_firn_air_content(firn_filename, x=bedmap3.x, y=bedmap3.y)
        thickness = bedmap3.ice_thickness
        bedmap3['ice_thickness'] = np.maximum(thickness - firn, 0.0).where(
            thickness.notnull()
        )
        bedmap3.ice_thickness.attrs = thickness.attrs
        bedmap3['ice_mask'] = ice_mask
        bedmap3['grounded_mask'] = grounded_mask
        bedmap3['ocean_mask'] = ocean_mask
        bedmap3['valid_mask'] = xr.ones_like(ocean_mask)

        # Remove all other variables
        varlist = [
            'base_elevation',
            'ice_draft',
            'ice_thickness',
            'ice_mask',
            'grounded_mask',
            'ocean_mask',
            'valid_mask',
        ]
        bedmap3 = bedmap3[varlist]

        # Write modified Bdemap3 to netCDF
        write_netcdf_with_fill_values(bedmap3, out_filename)
        logger.info('  Done.')

    def _create_target_scrip_file(self, files):
        """
        Create SCRIP file for either the x.xxxx degree (lat-lon) mesh or the
        NExxx (cubed-sphere) mesh, depending on the target grid
        References:
          https://acme-climate.atlassian.net/wiki/spaces/DOC/pages/872579110/
          Running+E3SM+on+New+Atmosphere+Grids
        """
        logger = self.logger
        logger.info(f'Create SCRIP file for {files.resolution_name} mesh')

        out_filename = files.target_scrip
        stem = pathlib.Path(out_filename).stem
        netcdf4_filename = f'{stem}.netcdf4.nc'

        # Build cubed sphere SCRIP file using tempestremap
        if files.exodus is not None:
            # Create EXODUS file
            args = [
                'GenerateCSMesh',
                '--alt',
                '--res',
                f'{files.resolution}',
                '--file',
                files.exodus,
            ]
            check_call(args, logger)

            # Create SCRIP file
            args = [
                'ConvertMeshToSCRIP',
                '--in',
                files.exodus,
                '--out',
                netcdf4_filename,
            ]
            check_call(args, logger)

        # Build lat-lon SCRIP file using pyremap
        else:
            descriptor = get_lat_lon_descriptor(
                dlon=files.resolution,
                dlat=files.resolution,
            )
            descriptor.to_scrip(netcdf4_filename)

        # writing out directly to NETCDF3_64BIT_DATA is either very slow or
        # unsupported, so use ncks
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            out_filename,
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _create_global_tiles(self, files):
        """
        Split the global dataset into lat/lon tiles to make remapping it
        tractable
        """
        logger = self.logger
        logger.info('Creating tiles of global data')
        os.makedirs('tiles', exist_ok=True)
        for tile in files.tiles:
            self._create_global_tile(
                global_filename=files.global_modified,
                lon_tile=tile.lon_tile,
                lat_tile=tile.lat_tile,
                out_filename=tile.source,
            )
        logger.info('  Done.')

    def _create_global_tile(
        self, global_filename, lon_tile, lat_tile, out_filename
    ):
        """
        Create a lat/lon tile of global data

        Parameters
        ----------
        global_filename : str
            name of the source global topography file
        lon_tile : int
            tile number along lon dim
        lat_tile : int
            tile number along lat dim
        out_filename : str
            name of the tile
        """
        logger = self.logger

        # Parse config
        config = self.config
        section = config['combine_topo']
        lat_tiles = section.getint('lat_tiles')
        lon_tiles = section.getint('lon_tiles')

        logger.info(f'    creating {out_filename}')

        # Load dataset
        ds = xr.open_dataset(global_filename)

        # Build lat and lon arrays for tile
        nlat = ds.sizes['lat']
        nlon = ds.sizes['lon']
        nlat_tile = nlat // lat_tiles
        nlon_tile = nlon // lon_tiles

        # Build tile latlon indices
        lat_indices = [lat_tile * nlat_tile, (lat_tile + 1) * nlat_tile]
        lon_indices = [lon_tile * nlon_tile, (lon_tile + 1) * nlon_tile]
        if lat_tile == lat_tiles - 1:
            lat_indices[1] = max([lat_indices[1], nlat])
        else:
            lat_indices[1] += 1
        if lon_tile == lon_tiles - 1:
            lon_indices[1] = max([lon_indices[1], nlon])
        else:
            lon_indices[1] += 1
        lat_index_array = np.arange(*lat_indices)
        lon_index_array = np.arange(*lon_indices)

        # Duplicate top and bottom rows to account for poles
        if lat_tile == 0:
            lat_index_array = np.insert(lat_index_array, 0, 0)
        if lat_tile == lat_tiles - 1:
            lat_index_array = np.append(lat_index_array, lat_index_array[-1])

        # Select tile from dataset
        tile = ds.isel(lat=lat_index_array, lon=lon_index_array)
        lat = tile.lat.values.copy()
        lat_attrs = tile.lat.attrs.copy()
        # xarray may expose coordinate views from ``isel()`` as read-only.
        # Reassign corrected pole coordinates instead of mutating in place,
        # while preserving CF metadata that ESMF uses to detect CFGRID files.
        if lat_tile == 0:
            lat[0] = -90.0  # Correct south pole
        if lat_tile == lat_tiles - 1:
            lat[-1] = 90.0  # Correct north pole
        tile = tile.assign_coords(
            lat=xr.DataArray(lat, dims=tile.lat.dims, attrs=lat_attrs)
        )

        # Write tile to netCDF
        write_netcdf_with_fill_values(tile, out_filename)

    def _create_antarctic_scrip_file(
        self, antarctic, in_filename, scrip_filename
    ):
        """
        Create SCRIP file for an antarctic dataset on a projection grid using
        pyremap
        """
        logger = self.logger
        logger.info('Creating Antarctic SCRIP file')

        proj4_string = DATASETS[antarctic]['proj4']
        mesh_name = DATASETS[antarctic]['mesh_name']
        netcdf4_filename = scrip_filename.replace('.nc', '.netcdf4.nc')

        # Define projection
        projection = pyproj.Proj(proj4_string)

        # Create SCRIP file using pyremap
        descriptor = ProjectionGridDescriptor.read(
            projection=projection,
            filename=in_filename,
            mesh_name=mesh_name,
        )
        descriptor.to_scrip(netcdf4_filename)

        # writing directly in NETCDF3_64BIT_DATA proved prohibitively slow
        # so we will use ncks to convert
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            scrip_filename,
        ]
        check_call(args, logger)

        logger.info('  Done.')
