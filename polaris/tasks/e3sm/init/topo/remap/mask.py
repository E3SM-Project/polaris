import os

import xarray as xr

from polaris import Step
from polaris.mesh.spherical.coastline import CONVENTIONS


class MaskTopoStep(Step):
    """
    A step to mask the global topograph dataset for ocean and land regions

    Attributes
    ----------
    combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
        The step for combining global and Antarctic topography on a cubed
        sphere grid
    """

    def __init__(self, component, combine_topo_step, name, subdir):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
            The step for combining global and Antarctic topography on a cubed
            sphere grid

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step
        """
        super().__init__(component, name=name, subdir=subdir)
        self.combine_topo_step = combine_topo_step
        self.add_output_file(filename='topography_masked.nc')

    def setup(self):
        """
        Set up the step in the work directory and set input files.
        """
        super().setup()

        combine_topo_step = self.combine_topo_step
        topo_filename = combine_topo_step.combined_filename

        self.add_input_file(
            filename='topography.nc',
            work_dir_target=os.path.join(
                combine_topo_step.path, topo_filename
            ),
        )

    def define_masks(self, ds):
        """
        Override in subclasses to return an ocean and a land mask array
        with the same shape as ``ds.base_elevation`` and other topogrpahy
        fields.  The masks are floating point arrays with values between 0
        and 1, where 1 indicates the cell is fully covered by land or ocean,
        respectively.

        The default implementation sets the ocean mask based on
        ``antarctic_boundary_convention`` and the land mask to locations where
        the base elevation is greater than 0 or the Antarctic ice sheet is
        present. The two overlap for Antarctic ice shelves, which are included
        in both masks.

        Parameters
        ----------
        ds : xarray.Dataset
            The dataset containing the topography fields

        Returns
        -------
        ocean_mask : xarray.DataArray
            The mask array with the same shape as the topography fields

        land_mask : xarray.DataArray
            The mask array with the same shape as the topography fields
        """
        config = self.config
        convention = self._get_antarctic_boundary_convention(config)
        base_elevation = ds.base_elevation
        ice_mask = ds.ice_mask

        below_sea_level = (base_elevation < 0.0).astype(float)
        above_sea_level = 1.0 - below_sea_level

        # above sea level or below sea leve but part of Antarcica
        land_mask = above_sea_level + below_sea_level * ice_mask

        ocean_mask = self._get_ocean_mask(
            base_elevation=base_elevation,
            ice_mask=ice_mask,
            grounded_mask=ds.grounded_mask,
            convention=convention,
        )

        return ocean_mask, land_mask

    @staticmethod
    def _get_antarctic_boundary_convention(config):
        """
        Get and validate the Antarctic boundary convention from config.
        """
        if not config.has_option(
            'spherical_mesh', 'antarctic_boundary_convention'
        ):
            raise ValueError(
                'Missing spherical_mesh.antarctic_boundary_convention '
                'in remap topography config.'
            )

        convention = config.get(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        if convention not in CONVENTIONS:
            valid = ', '.join(CONVENTIONS)
            raise ValueError(
                f'Unexpected antarctic_boundary_convention {convention!r}. '
                f'Valid options are: {valid}'
            )
        return convention

    @staticmethod
    def _get_ocean_mask(
        base_elevation,
        ice_mask,
        grounded_mask,
        convention,
    ):
        """
        Get the ocean mask before remapping.
        """
        below_sea_level = (base_elevation < 0.0).astype(float)

        if convention == 'calving_front':
            return below_sea_level * (1.0 - ice_mask)

        if convention == 'grounding_line':
            return below_sea_level * (1.0 - grounded_mask)

        if convention == 'bedrock_zero':
            return below_sea_level

        valid = ', '.join(CONVENTIONS)
        raise ValueError(
            f'Unexpected antarctic_boundary_convention {convention!r}. '
            f'Valid options are: {valid}'
        )

    def run(self):
        in_filename = 'topography.nc'
        out_filename = 'topography_masked.nc'
        logger = self.logger

        logger.info(f'Masking topography dataset {in_filename}')

        ds = xr.open_dataset(in_filename)

        var_names = list(ds.data_vars)

        logger.info('Creating ocean and land masks')
        masks = {}
        masks['ocean'], masks['land'] = self.define_masks(ds)

        logger.info('Applying ocean and land masks to topography dataset')
        for prefix in ['land', 'ocean']:
            mask = masks[prefix]
            for var in var_names:
                out_var = f'{prefix}_masked_{var}'
                ds[out_var] = ds[var] * mask
                ds[out_var].attrs = ds[var].attrs
            out_var = f'{prefix}_mask'
            ds[out_var] = mask

        ds.to_netcdf(out_filename)

        logger.info(f'Wrote masked topography dataset {out_filename}')
