import os
import pathlib
from glob import glob

import netCDF4
import numpy as np
import pyproj
import xarray as xr
from mpas_tools.logging import check_call
from pyremap import ProjectionGridDescriptor, get_lat_lon_descriptor

from polaris.parallel import run_command
from polaris.step import Step


class CombineStep(Step):
    """
    A step for combining global and antarctic topography datasets

    Attributes
    ----------
    resolution : float
        degrees (float) or face subdivisions (int)

    resolution_name: str
        either x.xxxx_degrees or NExxx

    combined_filename : str
        name of the combined topography file

    dst_scrip_filename : str
        name of the destination SCRIP file

    exodus_filename : str
        name of the exodus file for the cubed sphere mesh
    """

    # change these to update to the latest datasets
    ANTARCTIC = 'bedmap3'
    GLOBAL = 'gebco2023'

    DATASETS = {
        'bedmachinev3': {
            'filename': 'BedMachineAntarctica-v3.nc',
            'proj4': 'epsg:3031',
            'mesh_name': 'BedMachineAntarcticav3_500m',
        },
        'bedmap3': {
            'filename': 'bedmap3.nc',
            'proj4': 'epsg:3031',
            'mesh_name': 'Bedmap3_500m',
        },
        'gebco2023': {
            'filename': 'GEBCO_2023.nc',
            'mesh_name': 'GEBCO_2023',
        },
    }

    @staticmethod
    def get_subdir(low_res):
        """
        Get the subdirectory for the step based on the datasets
        Parameters
        ----------
        low_res : bool, optional
            Whether to use the low resolution configuration options
        """
        suffix = '_low_res' if low_res else ''
        subdir = (
            f'combine_{CombineStep.ANTARCTIC}_{CombineStep.GLOBAL}{suffix}'
        )
        return os.path.join('topo', subdir)

    def __init__(self, component, config, low_res=False):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        config : polaris.config.PolarisConfigParser
            The shared config options for the step

        low_res : bool, optional
            Whether to use the low resolution configuration options
        """
        antarctic_dataset = self.ANTARCTIC
        global_dataset = self.GLOBAL
        suffix = '_low_res' if low_res else ''
        name = f'combine_topo_{antarctic_dataset}_{global_dataset}{suffix}'
        subdir = self.get_subdir(low_res=low_res)
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=None,
            min_tasks=None,
        )
        self.resolution = None
        self.resolution_name = None
        self.combined_filename = None
        self.dst_scrip_filename = None
        self.exodus_filename = None

        # Set the config options for this step.  Since the shared config
        # file is in the step's work directory, we don't need a symlink
        self.set_shared_config(config)

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()

        config = self.config
        section = config['combine_topo']

        # Get input filenames and resolution
        antarctic_dataset = self.ANTARCTIC
        global_dataset = self.GLOBAL

        if antarctic_dataset not in self.DATASETS:
            raise ValueError(
                f'Unrecognized antarctic dataset: {antarctic_dataset}'
            )
        if global_dataset not in self.DATASETS:
            raise ValueError(f'Unrecognized global dataset: {global_dataset}')

        antarctic_filename = self.DATASETS[antarctic_dataset]['filename']
        global_filename = self.DATASETS[global_dataset]['filename']

        # Add topography data input files
        self.add_input_file(
            filename=antarctic_filename,
            target=antarctic_filename,
            database='topo',
        )
        self.add_input_file(
            filename=global_filename,
            target=global_filename,
            database='topo',
        )
        self._set_res_and_outputs(update=False)

        # Get ntasks and min_tasks
        self.ntasks = section.getint('ntasks')
        self.min_tasks = section.getint('min_tasks')

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
        self.ntasks = config.getint('combine_topo', 'ntasks')
        self.min_tasks = config.getint('combine_topo', 'min_tasks')
        super().constrain_resources(available_resources)

    def run(self):
        """
        Run this step
        """
        antarctic_dataset = self.ANTARCTIC
        global_dataset = self.GLOBAL
        antarctic_filename = self.DATASETS[antarctic_dataset]['filename']
        global_filename = self.DATASETS[global_dataset]['filename']

        self._set_res_and_outputs(update=True)

        if global_dataset in ['gebco2023']:
            in_filename = global_filename
            global_filename = global_filename.replace('.nc', '_cf.nc')
            self._modify_gebco(
                in_filename=in_filename,
                out_filename=global_filename,
            )

        if antarctic_dataset in ['bedmachinev3']:
            in_filename = antarctic_filename
            antarctic_filename = antarctic_filename.replace('.nc', '_mod.nc')
            self._modify_bedmachine(
                in_filename=in_filename,
                out_filename=antarctic_filename,
            )
        elif antarctic_dataset in ['bedmap3']:
            in_filename = antarctic_filename
            antarctic_filename = antarctic_filename.replace('.nc', '_mod.nc')
            self._modify_bedmap3(
                in_filename=in_filename,
                out_filename=antarctic_filename,
            )

        res_name = self.resolution_name
        assert res_name is not None, 'resolution_name should be set'
        global_remapped_filename = global_filename.replace(
            '.nc', f'_{res_name}.nc'
        )
        antartic_remapped_filename = antarctic_filename.replace(
            '.nc', f'_{res_name}.nc'
        )

        self._create_target_scrip_file()
        self._remap_global(
            global_filename=global_filename,
            out_filename=global_remapped_filename,
        )
        self._remap_antarctic(
            in_filename=antarctic_filename,
            remapped_filename=antartic_remapped_filename,
        )
        self._combine_datasets(
            antarctic_filename=antartic_remapped_filename,
            global_filename=global_remapped_filename,
            out_filename=self.combined_filename,
        )
        self._cleanup()

    def _set_res_and_outputs(self, update):
        """
        Set or update the resolution and output filenames based on config
        options
        """
        config = self.config
        section = config['combine_topo']
        target_grid = section.get('target_grid')

        if target_grid not in ['cubed_sphere', 'lat_lon']:
            raise ValueError(
                f'Unrecognized target grid: {target_grid}. '
                'Valid options are cubed_sphere or lat_lon'
            )

        # Get input filenames and resolution
        antarctic_dataset = self.ANTARCTIC
        global_dataset = self.GLOBAL

        # Parse resolution and update resolution attributes
        if target_grid == 'cubed_sphere':
            resolution = section.getint('resolution_cubedsphere')
            if update and resolution == self.resolution:
                # nothing to do
                return
            self.resolution = resolution
            self.resolution_name = f'ne{resolution}'
        elif target_grid == 'lat_lon':
            resolution = section.getfloat('resolution_latlon')
            if update and resolution == self.resolution:
                # nothing to do
                return
            self.resolution = resolution
            self.resolution_name = f'{resolution:.4f}_degree'

        # Start over with empty outputs
        self.outputs = []

        # Build output filenames
        res_name = self.resolution_name
        assert res_name is not None, 'resolution_name should be set'
        self.dst_scrip_filename = f'{self.resolution_name}.scrip.nc'
        self.combined_filename = '_'.join(
            [
                antarctic_dataset,
                global_dataset,
                f'{res_name}.nc',
            ]
        )
        self.exodus_filename = f'{self.resolution_name}.g'

        self.add_output_file(filename=self.dst_scrip_filename)
        self.add_output_file(filename=self.combined_filename)
        self.add_output_file(filename=self.exodus_filename)

        if update:
            # We need to set absolute paths
            step_dir = self.work_dir
            self.outputs = [
                os.path.abspath(os.path.join(step_dir, filename))
                for filename in self.outputs
            ]

    def _modify_gebco(self, in_filename, out_filename):
        """
        Modify GEBCO to include lon/lat bounds located at grid edges
        """
        logger = self.logger
        logger.info('Adding bounds to GEBCO lat/lon')

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

        # Write modified GEBCO to netCDF
        _write_netcdf_with_fill_values(gebco, out_filename)
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
        bedmachine.ice_draft.attrs['units'] = 'meters'
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
        _write_netcdf_with_fill_values(bedmachine, out_filename)
        logger.info('  Done.')

    def _modify_bedmap3(self, in_filename, out_filename):
        """
        Modify Bedmap3 to compute the fields needed by MPAS-Ocean
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
        bedmap3['ice_thickness'] = bedmap3.ice_thickness
        bedmap3['ice_draft'] = (
            bedmap3.surface_topography - bedmap3.ice_thickness
        )
        bedmap3.ice_draft.attrs['units'] = 'meters'
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
        _write_netcdf_with_fill_values(bedmap3, out_filename)
        logger.info('  Done.')

    def _create_global_tile(self, global_filename, lon_tile, lat_tile):
        """
        Create lat/lon tiles of global data to make processing more tractable

        Parameters
        ----------
        global_filename : str
            name of the source global topography file
        lon_tile : int
            tile number along lon dim
        lat_tile : int
            tile number along lat dim
        """
        logger = self.logger

        # Parse config
        config = self.config
        section = config['combine_topo']
        lat_tiles = section.getint('lat_tiles')
        lon_tiles = section.getint('lon_tiles')
        global_name = self.GLOBAL
        out_filename = f'tiles/{global_name}_tile_{lon_tile}_{lat_tile}.nc'

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
        lat_indices = np.arange(*lat_indices)
        lon_indices = np.arange(*lon_indices)

        # Duplicate top and bottom rows to account for poles
        if lat_tile == 0:
            lat_indices = np.insert(lat_indices, 0, 0)
        if lat_tile == lat_tiles - 1:
            lat_indices = np.append(lat_indices, lat_indices[-1])

        # Select tile from dataset
        tile = ds.isel(lat=lat_indices, lon=lon_indices)
        if lat_tile == 0:
            tile.lat.values[0] = -90.0  # Correct south pole
        if lat_tile == lat_tiles - 1:
            tile.lat.values[-1] = 90.0  # Correct north pole

        # Write tile to netCDF
        _write_netcdf_with_fill_values(tile, out_filename)

    def _create_antarctic_scrip_file(self, in_filename, scrip_filename):
        """
        Create SCRIP file for an antarctic dataset on a projection grid using
        pyremap
        """
        logger = self.logger
        logger.info('    Creating Antarctic SCRIP file')

        antarctic_dataset = self.ANTARCTIC
        proj4_string = self.DATASETS[antarctic_dataset]['proj4']
        mesh_name = self.DATASETS[antarctic_dataset]['mesh_name']
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

    def _create_target_scrip_file(self):
        """
        Create SCRIP file for either the x.xxxx degree (lat-lon) mesh or the
        NExxx (cubed-sphere) mesh, depending on the target grid
        References:
          https://acme-climate.atlassian.net/wiki/spaces/DOC/pages/872579110/
          Running+E3SM+on+New+Atmosphere+Grids
        """
        logger = self.logger
        logger.info(f'Create SCRIP file for {self.resolution_name} mesh')

        section = self.config['combine_topo']
        target_grid = section.get('target_grid')

        out_filename = self.dst_scrip_filename
        assert out_filename is not None, 'dst_scrip_filename should be set'
        stem = pathlib.Path(out_filename).stem
        netcdf4_filename = f'{stem}.netcdf4.nc'

        exodus_filename = self.exodus_filename

        # Build cubed sphere SCRIP file using tempestremap
        if target_grid == 'cubed_sphere':
            # Create EXODUS file
            args = [
                'GenerateCSMesh',
                '--alt',
                '--res',
                f'{self.resolution}',
                '--file',
                exodus_filename,
            ]
            check_call(args, logger)

            # Create SCRIP file
            args = [
                'ConvertMeshToSCRIP',
                '--in',
                exodus_filename,
                '--out',
                netcdf4_filename,
            ]
            check_call(args, logger)

        # Build lat-lon SCRIP file using pyremap
        elif target_grid == 'lat_lon':
            descriptor = get_lat_lon_descriptor(
                dlon=self.resolution,
                dlat=self.resolution,
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

    def _create_weights(self, in_filename, out_filename):
        """
        Create weights file for remapping to target grid. Filenames
        are passed as parameters so that the function can be applied to
        global and Antarctic.

        Parameters
        ----------
        in_filename : str
            source file name
        out_filename : str
            weights file name
        """
        config = self.config
        method = config.get('combine_topo', 'method')

        # Generate weights file
        args = [
            'ESMF_RegridWeightGen',
            '--source',
            in_filename,
            '--destination',
            self.dst_scrip_filename,
            '--weight',
            out_filename,
            '--method',
            method,
            '--netcdf4',
            '--src_regional',
            '--ignore_unmapped',
        ]
        run_command(
            args=args,
            cpus_per_task=self.cpus_per_task,
            ntasks=self.ntasks,
            openmp_threads=self.openmp_threads,
            config=config,
            logger=self.logger,
        )

    def _remap_to_target_grid(
        self,
        in_filename,
        mapping_filename,
        out_filename,
        default_dims=True,
    ):
        """
        Remap to target grid. Filenames are passed as parameters so
        that the function can be applied to global and Antarctic.

        Parameters
        ----------
        in_filename : str
            source file name
        mapping_filename : str
            weights file name
        out_filename : str
            remapped file name
        default_dims : bool
            default True, if False specify non-default source dims y,x
        """
        section = self.config['combine_topo']
        target_grid = section.get('target_grid')

        # Build command args
        args = ['ncremap', '-m', mapping_filename, '--vrb=1']

        # Add non-default gridding args
        regridArgs = []
        if not default_dims:
            regridArgs.extend(
                [
                    '--rgr lat_nm=y',
                    '--rgr lon_nm=x',
                ]
            )
        if target_grid == 'lat_lon':
            regridArgs.extend(
                [
                    '--rgr lat_nm_out=lat',
                    '--rgr lon_nm_out=lon',
                    '--rgr lat_dmn_nm=lat',
                    '--rgr lon_dmn_nm=lon',
                ]
            )
        if len(regridArgs) > 0:
            args.extend(['-R', ' '.join(regridArgs)])

        # Append input and output file names
        args.extend([in_filename, out_filename])

        # Remap to target grid
        check_call(args, self.logger)

    def _remap_global(self, global_filename, out_filename):
        """
        Remap global to target grid
        """
        logger = self.logger
        logger.info('Remapping global data')

        # Parse config
        config = self.config
        section = config['combine_topo']
        global_name = self.GLOBAL
        method = section.get('method')
        lat_tiles = section.getint('lat_tiles')
        lon_tiles = section.getint('lon_tiles')

        # Make tiles directory
        os.makedirs('tiles', exist_ok=True)

        # Initialize combined xarray.Dataset
        global_remapped = xr.Dataset()

        # Create tile maps and remapped tiles
        for lat_tile in range(lat_tiles):
            for lon_tile in range(lon_tiles):
                # File names
                tile_suffix = f'tile_{lon_tile}_{lat_tile}.nc'
                tile_filename = f'tiles/{global_name}_{tile_suffix}'
                mapping_filename = (
                    f'tiles/map_{global_name}_to_{self.resolution_name}'
                    f'_{method}_{tile_suffix}'
                )
                remapped_filename = (
                    f'tiles/{global_name}_{self.resolution_name}_{tile_suffix}'
                )

                # Call remapping functions
                self._create_global_tile(global_filename, lon_tile, lat_tile)
                self._create_weights(tile_filename, mapping_filename)
                self._remap_to_target_grid(
                    tile_filename,
                    mapping_filename,
                    remapped_filename,
                )

                # Add tile to remapped global topography
                logger.info(f'    adding {remapped_filename}')
                elevation = xr.open_dataset(remapped_filename).elevation
                elevation = elevation.where(elevation.notnull(), 0.0)
                if 'elevation' in global_remapped:
                    global_remapped['elevation'] = (
                        global_remapped.elevation + elevation
                    )
                else:
                    global_remapped['elevation'] = elevation

        # Write tile to netCDF
        logger.info(f'    writing {out_filename}')
        _write_netcdf_with_fill_values(global_remapped, out_filename)

        logger.info('  Done.')

    def _remap_antarctic(self, in_filename, remapped_filename):
        """
        Remap Antarctic dataset to target grid
        """
        logger = self.logger
        logger.info('Remapping Antarctic data')

        # Parse config
        config = self.config
        section = config['combine_topo']
        method = section.get('method')
        antartic_dataset = self.ANTARCTIC

        mesh_name = self.DATASETS[antartic_dataset]['mesh_name']

        # File names
        scrip_filename = in_filename.replace('.nc', '.scrip.nc')
        mapping_filename = (
            f'map_{mesh_name}_to_{self.resolution_name}_{method}.nc'
        )

        # Call remapping functions
        self._create_antarctic_scrip_file(
            in_filename=in_filename, scrip_filename=scrip_filename
        )
        self._create_weights(scrip_filename, mapping_filename)
        self._remap_to_target_grid(
            in_filename,
            mapping_filename,
            remapped_filename,
            default_dims=False,
        )

        logger.info('  Done.')

    def _combine_datasets(
        self, antarctic_filename, global_filename, out_filename
    ):
        """
        Combine remapped global and Antarctic datasets
        """
        logger = self.logger
        logger.info('Combine Antarctic and global datasets')

        config = self.config
        section = config['combine_topo']
        renorm_thresh = section.getfloat('renorm_thresh')

        out_filename = self.combined_filename
        stem = pathlib.Path(out_filename).stem
        netcdf4_filename = f'{stem}.netcdf4.nc'

        # Parse config
        config = self.config
        section = config['combine_topo']
        latmin = section.getfloat('latmin')
        latmax = section.getfloat('latmax')

        # Load and mask global dataset
        ds_global = xr.open_dataset(global_filename)
        global_elevation = ds_global.elevation
        global_elevation = global_elevation.where(
            global_elevation.notnull(), 0.0
        )

        # Load and mask Antarctic dataset
        ds_antarctic = xr.open_dataset(antarctic_filename)

        # renormalize variables
        denom = ds_antarctic.valid_mask
        renorm_mask = denom >= renorm_thresh
        denom = xr.where(renorm_mask, denom, 1.0)
        vars = [
            'base_elevation',
            'ice_thickness',
            'ice_draft',
            'ice_mask',
            'grounded_mask',
        ]

        for var in vars:
            attrs = ds_antarctic[var].attrs
            ds_antarctic[var] = (ds_antarctic[var] / denom).where(renorm_mask)
            ds_antarctic[var].attrs = attrs

        ant_bathy = ds_antarctic.base_elevation
        ant_bathy = ant_bathy.where(ant_bathy.notnull(), 0.0)

        # Blend data sets into combined data set
        combined = xr.Dataset()
        alpha = (ds_global.lat - latmin) / (latmax - latmin)
        alpha = np.maximum(np.minimum(alpha, 1.0), 0.0)
        combined['base_elevation'] = (
            alpha * global_elevation + (1.0 - alpha) * ant_bathy
        )

        # Add remaining Antarctic variables to combined Dataset
        for field in ['ice_draft', 'ice_thickness']:
            combined[field] = ds_antarctic[field]
        for field in ['base_elevation', 'ice_draft', 'ice_thickness']:
            combined[field].attrs['unit'] = 'meters'

        # Add masks
        for field in ['ice_mask', 'grounded_mask']:
            combined[field] = ds_antarctic[field]

        # Add fill values
        fill_vals = {
            'ice_draft': 0.0,
            'ice_thickness': 0.0,
            'ice_mask': 0.0,
            'grounded_mask': 0.0,
        }
        for field, fill_val in fill_vals.items():
            valid = combined[field].notnull()
            combined[field] = combined[field].where(valid, fill_val)

        # Save combined bathy to NetCDF
        _write_netcdf_with_fill_values(combined, netcdf4_filename)

        # writing directly in NETCDF3_64BIT_DATA proved prohibitively slow
        # so we will use ncks to convert
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            out_filename,
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _cleanup(self):
        """
        Clean up work directory
        """
        logger = self.logger
        logger.info('Cleaning up work directory')

        # Remove PETxxx.RegridWeightGen.Log files
        for f in glob('*.RegridWeightGen.Log'):
            os.remove(f)

        logger.info('  Done.')


def _write_netcdf_with_fill_values(ds, filename, format='NETCDF4'):
    """Write an xarray Dataset with NetCDF4 fill values where needed"""
    ds = ds.copy()
    fill_values = netCDF4.default_fillvals
    encoding = {}
    vars = list(ds.data_vars.keys()) + list(ds.coords.keys())
    for var_name in vars:
        # If there's already a fill value attribute, drop it
        ds[var_name].attrs.pop('_FillValue', None)
        is_numeric = np.issubdtype(ds[var_name].dtype, np.number)
        if is_numeric:
            dtype = ds[var_name].dtype
            for fill_type in fill_values:
                if dtype == np.dtype(fill_type):
                    encoding[var_name] = {'_FillValue': fill_values[fill_type]}
                    break
        else:
            encoding[var_name] = {'_FillValue': None}
    ds.to_netcdf(filename, encoding=encoding, format=format)
