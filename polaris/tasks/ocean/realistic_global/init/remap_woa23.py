import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step

from .woa23_map import WOA23_EXTRAP_FILENAME


class RemapWoa23Step(Step):
    """
    A step for applying the WOA23 mapping weights built by
    :py:class:`.Woa23MapStep`, remapping the extrapolated WOA23 hydrography
    product from the native 0.25-degree latitude-longitude grid to MPAS cell
    centres.

    This step is serial: the MPI work of building the mapping file happens in
    :py:class:`.Woa23MapStep`, and ``ncremap`` runs in serial here.

    Attributes
    ----------
    extrapolate_step : polaris.Step
        The upstream step that produces the extrapolated WOA23 product.

    woa23_map_step : polaris.Step
        The upstream step that builds the WOA23-to-mesh mapping file.
    """

    def __init__(self, component, subdir, extrapolate_step, woa23_map_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extrapolate_step : polaris.Step
            The step that produces ``woa23_decav_0.25_jan_extrap.nc``.

        woa23_map_step : polaris.Step
            The step that builds the WOA23-to-mesh mapping file.
        """
        super().__init__(
            component=component,
            name='remap_woa23',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.extrapolate_step = extrapolate_step
        self.woa23_map_step = woa23_map_step
        self.add_dependency(woa23_map_step, name='woa23_map')
        self.add_output_file('woa23_on_mesh.nc')

    def setup(self):
        """
        Declare the WOA23 input file.
        """
        super().setup()
        self.add_input_file(
            filename='woa23_extrap.nc',
            work_dir_target=os.path.join(
                self.extrapolate_step.path,
                WOA23_EXTRAP_FILENAME,
            ),
        )

    def run(self):
        """
        Remap WOA23 CT and SA from the 0.25-degree lat-lon source grid to
        MPAS cell centres, writing ``woa23_on_mesh.nc``.
        """
        logger = self.logger
        # the remapper (including the path to the mapping file it built) comes
        # from the map step, which has already run
        remapper = self.dependencies['woa23_map'].remapper

        remapper.ncremap(
            in_filename='woa23_extrap.nc',
            out_filename='woa23_on_mesh_raw.nc',
            variable_list=['ct_an', 'sa_an'],
            logger=logger,
        )

        ds_raw = xr.open_dataset('woa23_on_mesh_raw.nc')
        ds_out = self._postprocess_remapped_output(ds_raw)
        write_netcdf(ds_out, 'woa23_on_mesh.nc')

    @staticmethod
    def _postprocess_remapped_output(ds):
        """
        Clean up the raw ncremap output: rename ``ncol`` to ``nCells``,
        retain only ``ct_an`` and ``sa_an``, and ensure the ``depth``
        coordinate is preserved with the correct polarity convention
        (positive downward, in metres).

        Parameters
        ----------
        ds : xarray.Dataset
            Raw dataset produced by ncremap, with the horizontal dimension
            named ``ncol``.

        Returns
        -------
        xarray.Dataset
            Dataset with dimension ``nCells``, variables ``ct_an`` and
            ``sa_an``, and coordinate ``depth`` (positive downward).
        """
        if 'ncol' in ds.dims:
            ds = ds.rename({'ncol': 'nCells'})

        keep_vars = [v for v in ['ct_an', 'sa_an'] if v in ds]
        ds_out = ds[keep_vars]

        if 'depth' in ds.coords and 'depth' not in ds_out.coords:
            ds_out = ds_out.assign_coords(depth=ds['depth'])

        for var in keep_vars:
            ds_out[var].attrs = ds[var].attrs

        return ds_out
