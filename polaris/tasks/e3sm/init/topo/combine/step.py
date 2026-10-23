import os
import pathlib

import numpy as np
import xarray as xr
from mpas_tools.logging import check_call

from polaris.attrs import set_attrs
from polaris.cf import add_cf_conventions, drop_dangling_references
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.files import (
    ANTARCTIC,
    DATASETS,
    GLOBAL,
    get_combine_files,
    write_netcdf_with_fill_values,
)

#: variables in a combined topography file to compare against a baseline.
#: ``ocean_mask`` is deliberately left out.  The combine step writes it, but
#: the cached combined topography files that tasks use by default were
#: generated before it was added, so it is absent from the file a run
#: actually reads and from everything derived from it.  Add it back here
#: once those cached files have been regenerated.
COMBINE_TOPO_VALIDATE_VARS = [
    'base_elevation',
    'ice_draft',
    'ice_thickness',
    'ice_mask',
    'grounded_mask',
]


class CombineStep(Step):
    """
    A step for combining global and antarctic topography datasets.  It remaps
    them with the weights from
    :py:class:`polaris.tasks.e3sm.init.topo.combine.CombineWeightsStep` and
    blends them.

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

    prepare_step : polaris.tasks.e3sm.init.topo.combine.PrepareCombineStep
        The step that gets the datasets ready to remap

    weights_step : polaris.tasks.e3sm.init.topo.combine.CombineWeightsStep
        The step that makes the remapping weights
    """

    # the datasets are set in polaris.tasks.e3sm.init.topo.combine.files
    ANTARCTIC = ANTARCTIC
    GLOBAL = GLOBAL
    DATASETS = DATASETS

    @staticmethod
    def get_subdir():
        """
        Get the base subdirectory for the step based on the datasets.
        """
        subdir = f'combine_{CombineStep.ANTARCTIC}_{CombineStep.GLOBAL}'
        return os.path.join('topo', subdir)

    @classmethod
    def get_name(cls, target_grid, resolution_name):
        """
        Get the step name based on the current datasets and target grid.

        Parameters
        ----------
        target_grid : {'cubed_sphere', 'lat_lon'}
            The type of target grid for the combined topography

        resolution_name : str
            The target resolution name for the combined topography
        """
        return (
            f'combine_topo_{cls.ANTARCTIC}_{cls.GLOBAL}'
            f'_{target_grid}_{resolution_name}'
        )

    def __init__(
        self,
        component,
        subdir,
        target_grid,
        resolution_name,
        prepare_step,
        weights_step,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory within the component's work directory

        target_grid : {'cubed_sphere', 'lat_lon'}
            The type of target grid for the combined topography

        resolution_name : str
            The target resolution name for the combined topography

        prepare_step : polaris.tasks.e3sm.init.topo.combine.PrepareCombineStep
            The step that gets the datasets ready to remap

        weights_step : polaris.tasks.e3sm.init.topo.combine.CombineWeightsStep
            The step that makes the remapping weights
        """
        name = self.get_name(target_grid, resolution_name)
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.default_cached = True
        self.prepare_step = prepare_step
        self.weights_step = weights_step
        self.resolution = None
        self.resolution_name = None
        self.combined_filename = None
        self.dst_scrip_filename = None
        self.exodus_filename = None

    def setup(self):
        """
        Set up the step in the work directory, including linking the files
        from the steps that prepare the datasets and make the weights
        """
        super().setup()
        files = get_combine_files(self.config)
        self._set_res_and_outputs()

        prepare_path = self.prepare_step.path
        weights_path = self.weights_step.path
        inputs = {
            files.antarctic_modified: os.path.join(
                prepare_path, files.antarctic_modified
            ),
            files.antarctic_mapping: os.path.join(
                weights_path, files.antarctic_mapping
            ),
            # linked under other names, since this step makes its own links
            # to these, which are outputs of this step and in the cache
            _prepared(files.target_scrip): os.path.join(
                prepare_path, files.target_scrip
            ),
        }
        if files.exodus is not None:
            inputs[_prepared(files.exodus)] = os.path.join(
                prepare_path, files.exodus
            )
        for tile in files.tiles:
            inputs[tile.source] = os.path.join(prepare_path, tile.source)
            inputs[tile.mapping] = os.path.join(weights_path, tile.mapping)

        for filename, target in inputs.items():
            self.add_input_file(filename=filename, work_dir_target=target)

    def run(self):
        """
        Run this step
        """
        files = get_combine_files(self.config)

        self._link_target_grid(files)
        self._remap_global(files)
        self._remap_antarctic(files)
        self._combine_datasets(
            antarctic_filename=files.antarctic_remapped,
            global_filename=files.global_remapped,
            out_filename=self.combined_filename,
        )

    def _set_res_and_outputs(self):
        """
        Set the resolution and output filenames based on config options
        """
        files = get_combine_files(self.config)
        self.resolution = files.resolution
        self.resolution_name = files.resolution_name
        self.dst_scrip_filename = files.target_scrip
        self.combined_filename = files.combined
        self.exodus_filename = files.exodus

        # Start over with empty outputs
        self.outputs = []
        self.validate_vars = dict()

        self.add_output_file(filename=self.dst_scrip_filename)
        self.add_output_file(
            filename=self.combined_filename,
            validate_vars=COMBINE_TOPO_VALIDATE_VARS,
        )
        self.add_cf_check(self.combined_filename)
        if self.exodus_filename is not None:
            self.add_output_file(filename=self.exodus_filename)

    def _link_target_grid(self, files):
        """
        Hard-link the target grid's files from the prepare step, so that
        they are outputs of this step, as they are in the cache, without
        copying them.  A symbolic link would make the two steps produce the
        same file.
        """
        filenames = [files.target_scrip]
        if files.exodus is not None:
            filenames.append(files.exodus)
        for filename in filenames:
            if os.path.lexists(filename):
                os.remove(filename)
            os.link(os.path.realpath(_prepared(filename)), filename)

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

    def _remap_global(self, files):
        """
        Remap global to target grid
        """
        logger = self.logger
        logger.info('Remapping global data')

        # Initialize combined xarray.Dataset
        global_remapped = xr.Dataset()

        # Remap tiles
        for tile in files.tiles:
            self._remap_to_target_grid(
                tile.source,
                tile.mapping,
                tile.remapped,
            )

            # Add tile to remapped global topography
            logger.info(f'    adding {tile.remapped}')
            ds_tile = xr.open_dataset(tile.remapped)
            for field in ['elevation', 'ocean_mask']:
                da = ds_tile[field]
                da = da.where(da.notnull(), 0.0)
                if field in global_remapped:
                    global_remapped[field] = global_remapped[field] + da
                else:
                    global_remapped[field] = da

        # Write tile to netCDF
        out_filename = files.global_remapped
        logger.info(f'    writing {out_filename}')
        write_netcdf_with_fill_values(global_remapped, out_filename)

        logger.info('  Done.')

    def _remap_antarctic(self, files):
        """
        Remap Antarctic dataset to target grid
        """
        logger = self.logger
        logger.info('Remapping Antarctic data')

        self._remap_to_target_grid(
            files.antarctic_modified,
            files.antarctic_mapping,
            files.antarctic_remapped,
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
        global_ocean_mask = ds_global.ocean_mask
        global_ocean_mask = global_ocean_mask.where(
            global_ocean_mask.notnull(), 0.0
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
            'ocean_mask',
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

        # Add masks
        for field in ['ice_mask', 'grounded_mask']:
            combined[field] = ds_antarctic[field]
        antarctic_ocean_mask = ds_antarctic.ocean_mask.where(
            ds_antarctic.ocean_mask.notnull(), global_ocean_mask
        )
        combined['ocean_mask'] = (
            alpha * global_ocean_mask + (1.0 - alpha) * antarctic_ocean_mask
        )

        # Add fill values
        fill_vals = {
            'ice_draft': 0.0,
            'ice_thickness': 0.0,
            'ice_mask': 0.0,
            'grounded_mask': 0.0,
            'ocean_mask': 0.0,
        }
        for field, fill_val in fill_vals.items():
            valid = combined[field].notnull()
            combined[field] = combined[field].where(valid, fill_val)

        _label_combined_fields(combined)

        # Save combined bathy to NetCDF.  The lat and lon bounds of the
        # source grids do not come along.
        combined = add_cf_conventions(drop_dangling_references(combined))
        write_netcdf_with_fill_values(combined, netcdf4_filename)

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


def _prepared(filename):
    """The name of the link to a file from the prepare step"""
    return f'prepared_{filename}'


def _label_combined_fields(combined):
    """
    Give each combined topography field its own metadata.

    Every field here is derived from something else -- ``base_elevation`` and
    ``ocean_mask`` by blending with a latitude-derived ``alpha``, the ice
    fields by renormalizing and remapping the Antarctic dataset -- and xarray
    propagates ``attrs`` through all of that.  Left alone they inherit
    whatever their parents carried: ``base_elevation`` picked up latitude's
    ``axis``, ``valid_min``, ``valid_max`` and ``bounds``, ``ocean_mask``
    claimed ``standard_name = latitude`` alongside Bedmap3's surface-type
    ``flag_values``, and ``grounded_mask`` called itself an ice mask.

    Assigning wholesale is what drops the inherited keys; setting only
    ``units`` would leave the rest of them in place.  Everything downstream of
    the combined topography inherits from here in turn, so this is the place
    to get it right.

    ``ice_thickness`` keeps the CF ``standard_name`` it arrives with from
    BedMachine/Bedmap3, since that one really does describe what it holds.
    The other five have no ``standard_name``: a couple of CF names look like
    candidates (``bedrock_altitude``, ``sea_area_fraction``), but none has
    been checked against the standard-name table, and an unverified one is
    worse than none.
    """
    fractions = {
        'ice_mask': 'fraction of the cell covered by ice',
        'grounded_mask': 'fraction of the cell covered by grounded ice',
        'ocean_mask': 'fraction of the cell covered by ocean',
    }
    heights = {
        'base_elevation': 'bedrock elevation above sea level',
        'ice_draft': 'elevation of the ice-ocean interface',
        'ice_thickness': 'ice thickness',
    }
    standard_names = {'ice_thickness': 'land_ice_thickness'}
    for field, long_name in fractions.items():
        set_attrs(combined[field], long_name=long_name, units='1')
    for field, long_name in heights.items():
        set_attrs(combined[field], long_name=long_name, units='m')
    for field, standard_name in standard_names.items():
        combined[field].attrs['standard_name'] = standard_name
