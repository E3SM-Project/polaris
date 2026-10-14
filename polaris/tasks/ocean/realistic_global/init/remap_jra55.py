import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    JRA55_STRESS_FILENAME,
)

JRA55_ON_MESH_FILENAME = 'jra55_on_mesh.nc'


class RemapJra55Step(Step):
    """
    A step for applying the JRA55-do mapping weights built by
    :py:class:`.Jra55MapStep`, remapping the wind-stress product from the
    native TL319 grid to MPAS cell centers.

    Every cell of the culled mesh has to be covered by the weights.
    ``ncremap`` writes zero rather than a missing value to a cell the weights
    do not reach, so the step checks the coverage recorded in the mapping
    file and fails rather than let a gap reach the forcing file as zero
    stress.

    Attributes
    ----------
    stress_step : polaris.Step
        The upstream step that produces the JRA55-do wind-stress product.

    jra55_map_step : polaris.Step
        The upstream step that builds the JRA55-to-mesh mapping file.
    """

    def __init__(self, component, subdir, stress_step, jra55_map_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stress_step : polaris.Step
            The step that produces the JRA55-do wind-stress product.

        jra55_map_step : polaris.Step
            The step that builds the JRA55-to-mesh mapping file.
        """
        super().__init__(
            component=component,
            name='remap_jra55',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.stress_step = stress_step
        self.jra55_map_step = jra55_map_step
        self.add_dependency(jra55_map_step, name='jra55_map')
        self.add_output_file(JRA55_ON_MESH_FILENAME)

    def setup(self):
        """
        Declare the JRA55-do input file.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_STRESS_FILENAME,
            work_dir_target=os.path.join(
                self.stress_step.path,
                JRA55_STRESS_FILENAME,
            ),
        )

    def run(self):
        """
        Remap the wind stress to MPAS cell centers, check that no cell is
        missing, and write ``jra55_on_mesh.nc``.
        """
        logger = self.logger
        # the remapper (including the path to the mapping file it built)
        # comes from the map step, which has already run
        remapper = self.dependencies['jra55_map'].remapper

        remapper.ncremap(
            in_filename=JRA55_STRESS_FILENAME,
            out_filename='jra55_on_mesh_raw.nc',
            variable_list=['taux', 'tauy'],
            logger=logger,
        )

        with xr.open_dataset(remapper.map_filename) as ds_map:
            frac_b = ds_map.frac_b.values

        with xr.open_dataset('jra55_on_mesh_raw.nc') as ds_raw:
            ds_out = self._postprocess_remapped_output(ds_raw).load()

        check_no_missing_cells(
            ds=ds_out, var_names=['taux', 'tauy'], frac_b=frac_b
        )

        write_netcdf(ds_out, JRA55_ON_MESH_FILENAME)

    @staticmethod
    def _postprocess_remapped_output(ds):
        """
        Clean up the raw ncremap output: rename ``ncol`` to ``nCells`` and
        retain only ``taux`` and ``tauy``.

        Parameters
        ----------
        ds : xarray.Dataset
            Raw dataset produced by ncremap, with the horizontal dimension
            named ``ncol``.

        Returns
        -------
        xarray.Dataset
            Dataset with dimension ``nCells`` and variables ``taux`` and
            ``tauy``.
        """
        if 'ncol' in ds.dims:
            ds = ds.rename({'ncol': 'nCells'})

        keep_vars = [var for var in ['taux', 'tauy'] if var in ds]
        ds_out = ds[keep_vars]
        for var in keep_vars:
            ds_out[var].attrs = ds[var].attrs

        return ds_out


def check_no_missing_cells(ds, var_names, frac_b, tolerance=1.0e-6):
    """
    Raise an error if any cell is missing from the remapped wind stress.

    A cell is missing if the mapping weights do not fully cover it or if any
    of ``var_names`` is not finite there.  The coverage has to come from the
    mapping file: ``ncremap`` writes zero, not a missing value, to a cell
    the weights do not reach when the source has no ``_FillValue``.

    Parameters
    ----------
    ds : xarray.Dataset
        The remapped dataset, with the given variables on an ``nCells``
        dimension

    var_names : list of str
        The variables to check

    frac_b : numpy.ndarray
        The fraction of each destination cell covered by the source grid,
        from the mapping file

    tolerance : float, optional
        How far below one the coverage of a cell may be before the cell
        counts as missing
    """
    missing = frac_b < 1.0 - tolerance
    for var in var_names:
        missing |= ~np.isfinite(ds[var].values)

    n_missing = int(np.count_nonzero(missing))
    if n_missing > 0:
        raise ValueError(
            f'{n_missing} of {missing.size} cells have no remapped wind '
            f'stress.  Bilinear remapping of the JRA55-do product is '
            f'expected to cover every cell of the culled mesh.'
        )
