import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call
from pyremap import MpasCellMeshDescriptor

from polaris import Step
from polaris.io import symlink
from polaris.parallel import run_command


class RemapTopoStep(Step):
    """
    A step for remapping topography data such as base elevation and ice sheet
    properites from a cubed-sphere grid to a global MPAS base mesh.

    Note: This step cannot descend from
    {py:class}`polaris.remap.MappingFileStep` because the soruce mesh is a
    cubed-sphere grid, which is not currently supported by pyremap.

    Attributes
    ----------
    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step

    combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
        The step for combining global and Antarctic topography on a cubed
        sphere grid

    mask_topo_step : polaris.tasks.e3sm.init.topo.MaskTopoStep
        The step that applies a mask to a global topography dataset on a cubed
        sphere grid

    smoothing : bool, optional
        Whether smoothing will be applied as part of the remapping

    unsmoothed_topo : polaris.tasks.e3sm.init.topo.RemapTopoStep, optional
        A step with unsmoothed topography

    expand_distance : float or xarray.DataArray
        The distance to expand the topography mask

    expand_factor : float or xarray.DataArray
        The factor to expand the topography mask

    do_remapping : bool
        Whether to remap the topography.  If False, the step will symlink
        to the unsmoothed topography file.
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        combine_topo_step,
        mask_topo_step,
        name,
        subdir,
        smoothing=False,
        unsmoothed_topo=None,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The base mesh step containing input files to this step

        combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
            The step for combining global and Antarctic topography on a cubed
            sphere grid

        mask_topo_step : polaris.tasks.e3sm.init.topo.MaskTopoStep
            The step that applies a mask to a global topography dataset on a
            cubed sphere grid

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step

        smoothing : bool, optional
            Whether smoothing will be applied as part of the remapping

        unsmoothed_topo : polaris.tasks.e3sm.init.topo.RemapTopoStep, optional
            A step with unsmoothed topography
        """
        super().__init__(
            component, name=name, subdir=subdir, ntasks=1, min_tasks=1
        )
        self.base_mesh_step = base_mesh_step
        self.combine_topo_step = combine_topo_step
        self.mask_topo_step = mask_topo_step
        self.smoothing = smoothing
        self.unsmoothed_topo = unsmoothed_topo

        self.add_output_file(filename='topography_remapped.nc')
        self.expand_distance = 0.0
        self.expand_factor = 1.0
        self.do_remapping = True

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()
        config = self.config
        section = config['remap_topography']

        base_path = self.base_mesh_step.path
        base_filename = self.base_mesh_step.config.get(
            'spherical_mesh',
            'mpas_mesh_filename',
        )
        target = os.path.join(base_path, base_filename)
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        combine_topo_step = self.combine_topo_step
        src_scrip_filename = combine_topo_step.dst_scrip_filename

        masked_topo_step = self.mask_topo_step
        topo_filename = 'topography_masked.nc'

        self.add_input_file(
            filename='topography.nc',
            work_dir_target=os.path.join(masked_topo_step.path, topo_filename),
        )
        self.add_input_file(
            filename='source.scrip.nc',
            work_dir_target=os.path.join(
                combine_topo_step.path, src_scrip_filename
            ),
        )

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
        section = config['remap_topography']
        self.ntasks = section.getint('ntasks')
        self.min_tasks = section.getint('min_tasks')
        super().constrain_resources(available_resources)

    def define_smoothing(self, ds_unsmoothed):
        """
        Define smoothing ``expand_distance`` and ``expand_factor`` fields.
        Derived classes should override this method to create spatially
        varying smoothing fields.  An ``expand_distance`` of 0.0 and an
        ``expand_factor`` of 1.0 will not smooth the topography

        The default implementation returns constant values from the config
        file.

        Parameters
        ----------
        ds_unsmoothed : polaris.tasks.e3sm.init.topo.RemapTopoStep
            The step with unsmoothed topography

        Returns
        -------
        expand_distance : xarray.DataArray or float
            The distance to expand the topography mask, same shape as
            fields in ``ds_unsmoothed`` if not constant

        expand_factor : xarray.DataArray or float
            The factor to expand the topography mask, same shape as
            fields in ``ds_unsmoothed`` if not constant
        """
        config = self.config
        section = config['remap_topography']
        expand_distance = section.getfloat('expand_distance')
        expand_factor = section.getfloat('expand_factor')

        return expand_distance, expand_factor

    def run(self):
        """
        Run this step of the test case
        """
        super().run()
        self._setup_smoothing()

        if self.do_remapping:
            self._create_target_scrip_file()
            self._create_weights()
            self._remap_to_target()
            self._renormalize_remapped_topo()

    def _setup_smoothing(self):
        """
        If we are smoothing but no smoothing was actually requested, symlink
        to the unsmoothed topography
        """
        if self.smoothing and self.unsmoothed_topo is not None:
            unsmoothed_filename = 'topography_unsmoothed.nc'
            target_filename = 'topography_remapped.nc'
            unsmoothed_path = self.unsmoothed_topo.work_dir
            target = os.path.join(unsmoothed_path, target_filename)
            symlink(target, unsmoothed_filename)

            ds_unsmoothed = xr.open_dataset(unsmoothed_filename)
            self.expand_distance, self.expand_factor = self.define_smoothing(
                ds_unsmoothed
            )

            if self.expand_distance == 0.0 and self.expand_factor == 1.0:
                # we already have unsmoothed topography and we're not doing
                # smoothing so we can just symlink the unsmoothed results
                symlink(unsmoothed_filename, target_filename)

                self.do_remapping = False

    def _create_target_scrip_file(self):
        """
        Create target SCRIP file from MPAS mesh file.
        """
        logger = self.logger
        logger.info('Create source SCRIP file')
        netcdf4_filename = 'target.scrip.netcdf4.nc'

        mesh_name = self.base_mesh_step.mesh_name

        descriptor = MpasCellMeshDescriptor(
            filename='base_mesh.nc',
            mesh_name=mesh_name,
        )
        descriptor.to_scrip(
            netcdf4_filename,
            expand_dist=self.expand_distance,
            expand_factor=self.expand_factor,
        )

        # writing directly in NETCDF3_64BIT_DATA proved prohibitively slow
        # so we will use ncks to convert
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            'target.scrip.nc',
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _create_weights(self):
        """
        Create mapping weights file using mbtempest
        """
        logger = self.logger
        logger.info('Create weights file')

        method = 'conserve'

        args = [
            'mbtempest',
            '--type',
            '5',
            '--load',
            'source.scrip.nc',
            '--load',
            'target.scrip.nc',
            '--file',
            f'map_source_to_target_{method}.nc',
            '--weights',
            '--gnomonic',
            '--boxeps',
            '1e-9',
        ]

        run_command(
            args,
            self.cpus_per_task,
            self.ntasks,
            self.openmp_threads,
            self.config,
            self.logger,
        )

        logger.info('  Done.')

    def _remap_to_target(self):
        """
        Remap topography onto MPAS target mesh
        """
        logger = self.logger
        logger.info('Remap to target')

        method = 'conserve'

        # Build command args
        args = [
            'ncremap',
            '-m',
            f'map_source_to_target_{method}.nc',
            '--vrb=1',
            'topography.nc',
            'topography_ncremap.nc',
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _renormalize_remapped_topo(self):
        """
        Renormalize the topography by the ocean and land fractions
        """
        logger = self.logger
        logger.info('Renormalize remapped topography')

        config = self.config
        section = config['remap_topography']
        renorm_threshold = section.getfloat('renorm_threshold')

        ds_in = xr.open_dataset('topography_ncremap.nc')
        ds_in = ds_in.rename({'ncol': 'nCells'})

        drop_vars = [
            'lat',
            'lon',
            'lat_vertices',
            'lon_vertices',
            'area',
            'x',
            'y',
        ]
        ds_in = ds_in.drop_vars(drop_vars)

        masks = {}
        norms = {}

        ds_out = xr.Dataset()

        for prefix in ['land', 'ocean']:
            fraction = ds_in[f'{prefix}_mask']
            # fraction should not exceed 1.0
            fraction = np.minimum(fraction, 1.0)
            ds_out[f'{prefix}_frac'] = fraction
            mask = fraction > renorm_threshold
            norm = xr.where(mask, 1.0 / fraction, 0.0)
            masks[prefix] = mask
            norms[prefix] = norm

        for var in ds_in.data_vars:
            if var.endswith('mask'):
                # let's call it a fraction ("frac") after remapping
                var_out = f'{var[:-4]}frac'
                # don't renormalize the fractional variables
                # but make sure they do not exceed 1.0
                ds_out[var_out] = np.minimum(ds_in[var], 1.0)
            elif 'masked' in var:
                # a masked variable that isn't a fraction, so we need to
                # renormalize it
                prefix = var.split('_')[0]
                var_out = var
                ds_out[var_out] = norms[prefix] * ds_in[var].where(
                    masks[prefix]
                )
            else:
                # not a mask or masked variable, so we just copy it
                var_out = var
                ds_out[var_out] = ds_in[var]

            ds_out[var_out].attrs = ds_in[var].attrs

        write_netcdf(ds_out, 'topography_remapped.nc')

        logger.info('  Done.')
