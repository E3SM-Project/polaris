import os

import numpy as np
import xarray as xr
from mpas_tools.io import open_dataset, write_netcdf
from mpas_tools.logging import check_call

from polaris import Step
from polaris.cf import add_cf_conventions
from polaris.io import symlink
from polaris.tasks.e3sm.init.topo.combine.step import (
    COMBINE_TOPO_VALIDATE_VARS,
)
from polaris.tasks.e3sm.init.topo.remap.weights import MAPPING_FILENAME


def get_remapped_topo_validate_vars():
    """
    Get the variables in the remapped topography file that should be compared
    against a baseline

    Returns
    -------
    validate_vars : list of str
        The remapped topography variables and fractions, both unmasked and
        masked by the ocean and land fractions
    """
    validate_vars = [_frac_name(var) for var in COMBINE_TOPO_VALIDATE_VARS]
    # the ocean and land masks that the mask-topography step adds become
    # fractions, too
    validate_vars.extend(['ocean_frac', 'land_frac'])
    for prefix in ['land', 'ocean']:
        validate_vars.extend(
            f'{prefix}_masked_{_frac_name(var)}'
            for var in COMBINE_TOPO_VALIDATE_VARS
        )
    return validate_vars


def _frac_name(var):
    """
    Get the name a variable takes after remapping, where masks become
    fractions
    """
    if var.endswith('mask'):
        return f'{var[:-4]}frac'
    return var


class RemapTopoStep(Step):
    """
    A step for remapping topography data such as base elevation and ice sheet
    properties from a cubed-sphere grid to a global MPAS base mesh, using the
    weights from
    {py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoWeightsStep`.

    Note: The step for making the weights cannot descend from
    {py:class}`polaris.remap.MappingFileStep` because the source mesh is a
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

    prepare_step : polaris.tasks.e3sm.init.topo.remap.PrepareRemapTopoStep
        The step that decides on smoothing and makes the SCRIP file for the
        MPAS mesh

    weights_step : polaris.tasks.e3sm.init.topo.remap.RemapTopoWeightsStep
        The step that makes the remapping weights

    smoothing : bool, optional
        Whether smoothing will be applied as part of the remapping

    unsmoothed_topo : polaris.tasks.e3sm.init.topo.RemapTopoStep, optional
        A step with unsmoothed topography

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
        prepare_step,
        weights_step,
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

        prepare_step : polaris.tasks.e3sm.init.topo.remap.PrepareRemapTopoStep
            The step that decides on smoothing and makes the SCRIP file for
            the MPAS mesh

        weights_step : polaris.tasks.e3sm.init.topo.remap.RemapTopoWeightsStep
            The step that makes the remapping weights

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
        self.prepare_step = prepare_step
        self.weights_step = weights_step
        self.smoothing = smoothing
        self.unsmoothed_topo = unsmoothed_topo
        self.do_remapping = True

        # whether there is remapping to do is decided by the prepare step
        # when it runs, and the weights exist only if there is, so both
        # steps are found through dependencies rather than input files
        self.add_dependency(prepare_step, name='prepare')
        self.add_dependency(weights_step, name='weights')

        self.add_output_file(
            filename='topography_remapped.nc',
            validate_vars=get_remapped_topo_validate_vars(),
        )
        self.add_cf_check('topography_remapped.nc')

    def setup(self):
        """
        Set up the step in the work directory, including linking input files
        """
        super().setup()

        masked_topo_step = self.mask_topo_step
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=os.path.join(
                masked_topo_step.path, 'topography_masked.nc'
            ),
        )

        if self.smoothing and self.unsmoothed_topo is not None:
            self.add_input_file(
                filename='topography_unsmoothed.nc',
                work_dir_target=os.path.join(
                    self.unsmoothed_topo.path, 'topography_remapped.nc'
                ),
            )

    def run(self):
        """
        Run this step of the test case
        """
        self.do_remapping = self.dependencies['prepare'].do_remapping
        if not self.do_remapping:
            # we already have unsmoothed topography and we're not doing
            # smoothing so we can just symlink the unsmoothed results
            symlink('topography_unsmoothed.nc', 'topography_remapped.nc')
            return

        mapping_filename = os.path.join(
            self.dependencies['weights'].work_dir, MAPPING_FILENAME
        )
        self._remap_to_target(mapping_filename)
        self._renormalize_remapped_topo()

    def _remap_to_target(self, mapping_filename):
        """
        Remap topography onto MPAS target mesh
        """
        logger = self.logger
        logger.info('Remap to target')

        # Build command args
        args = [
            'ncremap',
            '-m',
            mapping_filename,
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

        ds_in = open_dataset('topography_ncremap.nc')
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

            ds_out[var_out].attrs = dict(ds_in[var].attrs)

        _clean_remapped_attrs(ds_out)

        write_netcdf(add_cf_conventions(ds_out), 'topography_remapped.nc')

        logger.info('  Done.')


def _clean_remapped_attrs(ds_out):
    """
    Drop the CF attributes that no longer describe the remapped topography.

    ``ncremap`` adds ``cell_measures = 'area: area'`` and
    ``coordinates = 'lat lon'`` to everything it writes, and this step drops
    ``area``, ``lat`` and ``lon``.  Both attributes are therefore left naming
    variables that are not in the file.

    ``grid_mapping`` comes the other way, in from the projected Antarctic
    source data, and names a ``mapping`` variable that does not survive
    remapping to the MPAS mesh either.

    xarray moves ``coordinates`` from a variable's attributes into its
    encoding when it reads a file, and writes it back from there, so it has
    to be dropped from both.
    """
    dangling = ['cell_measures', 'coordinates', 'grid_mapping']
    for var in ds_out.data_vars:
        for attr in dangling:
            ds_out[var].attrs.pop(attr, None)
            ds_out[var].encoding.pop(attr, None)
