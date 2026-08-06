import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from scipy.spatial import cKDTree

from polaris import Step
from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    JRA55_STRESS_FILENAME,
)

JRA55_ON_MESH_FILENAME = 'jra55_on_mesh.nc'


class RemapJra55Step(Step):
    """
    A step for applying the JRA55-do mapping weights built by
    :py:class:`.Jra55MapStep`, remapping the wind-stress product from the
    native TL319 grid to MPAS cell centres.

    mbtempest's bilinear coverage stops at the source grid's extrapolated
    cell corner, 89.8485 degrees N for TL319, leaving a cap of about 891
    km^2 unmapped at the North Pole.  That is smaller than one cell on any
    mesh coarser than about 30 km and roughly nine cells at 10 km; the South
    Pole is Antarctic land and is culled.  Those cells take the value of
    their nearest valid neighbour.

    Padding the source grid to close the cap is *not* an option: it aborts
    mbtempest.  See ``remap_bilinear_pole_findings.md``.

    Attributes
    ----------
    stress_step : polaris.Step
        The upstream step that produces the JRA55-do wind-stress product.

    jra55_map_step : polaris.Step
        The upstream step that builds the JRA55-to-mesh mapping file.

    cull_mesh_step : polaris.Step
        The upstream cull-mesh step, whose mesh supplies the cell locations
        used to find nearest valid neighbours.
    """

    def __init__(
        self,
        component,
        subdir,
        stress_step,
        jra55_map_step,
        cull_mesh_step,
    ):
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

        cull_mesh_step : polaris.Step
            The step that produces ``culled_ocean_mesh.nc``.
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
        self.cull_mesh_step = cull_mesh_step
        self.add_dependency(jra55_map_step, name='jra55_map')
        self.add_output_file(JRA55_ON_MESH_FILENAME)

    def setup(self):
        """
        Declare the JRA55-do and mesh input files.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_STRESS_FILENAME,
            work_dir_target=os.path.join(
                self.stress_step.path,
                JRA55_STRESS_FILENAME,
            ),
        )
        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )

    def run(self):
        """
        Remap the wind stress to MPAS cell centres, fill the residual polar
        cells, and write ``jra55_on_mesh.nc``.
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

        with xr.open_dataset('jra55_on_mesh_raw.nc') as ds_raw:
            ds_out = self._postprocess_remapped_output(ds_raw)

        with xr.open_dataset('culled_mesh.nc') as ds_mesh:
            cell_xyz = np.column_stack(
                [
                    ds_mesh.xCell.values,
                    ds_mesh.yCell.values,
                    ds_mesh.zCell.values,
                ]
            )

        section = self.config['realistic_global_init']
        ds_out, n_filled = fill_missing_from_nearest(
            ds=ds_out,
            var_names=['taux', 'tauy'],
            cell_xyz=cell_xyz,
            max_fill_fraction=section.getfloat('max_polar_fill_fraction'),
            min_allowed_fill=section.getint('min_allowed_polar_fill'),
        )
        logger.info(
            f'Filled {n_filled} polar cell(s) of {cell_xyz.shape[0]} from '
            f'their nearest valid neighbour'
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


def fill_missing_from_nearest(
    ds, var_names, cell_xyz, max_fill_fraction, min_allowed_fill
):
    """
    Fill cells with missing values from their nearest valid neighbour.

    A cell is considered missing if *any* of ``var_names`` is not finite
    there, so the components of a vector are always filled from the same
    donor cell and the filled vector stays physical.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with the given variables on an ``nCells`` dimension

    var_names : list of str
        The variables to fill

    cell_xyz : numpy.ndarray
        An ``nCells`` x 3 array of Cartesian cell-centre coordinates

    max_fill_fraction : float
        Raise if the fraction of missing cells exceeds this.  The expected
        gap is the ~891 km^2 polar cap, so a large count means something
        other than the pole is wrong and should not be filled silently.

    min_allowed_fill : int
        Always allow at least this many cells to be filled, so that coarse
        meshes with only a handful of cells near the pole do not trip the
        fraction test.

    Returns
    -------
    ds : xarray.Dataset
        The dataset with missing values filled

    n_missing : int
        The number of cells that were filled
    """
    n_cells = cell_xyz.shape[0]
    valid = np.ones(n_cells, dtype=bool)
    for var in var_names:
        valid &= np.isfinite(ds[var].values)

    n_missing = int(np.count_nonzero(~valid))
    if n_missing == 0:
        return ds, 0

    allowed = max(min_allowed_fill, int(max_fill_fraction * n_cells))
    if n_missing > allowed:
        raise ValueError(
            f'{n_missing} of {n_cells} cells have no remapped wind stress, '
            f'more than the {allowed} expected from the small polar cap '
            f'that bilinear remapping leaves uncovered.  Something other '
            f'than the pole is wrong; refusing to fill.'
        )
    if not valid.any():
        raise ValueError('No valid cells to fill missing wind stress from')

    tree = cKDTree(cell_xyz[valid])
    _, nearest = tree.query(cell_xyz[~valid])
    for var in var_names:
        values = ds[var].values.copy()
        values[~valid] = values[valid][nearest]
        ds[var] = xr.DataArray(
            data=values, dims=ds[var].dims, attrs=ds[var].attrs
        )

    return ds, n_missing
