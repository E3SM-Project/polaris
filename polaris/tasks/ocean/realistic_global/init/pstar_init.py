import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.vertical.pstar_init import PStarInitStep


class RealisticPStarInitStep(PStarInitStep):
    """
    A step that jointly initializes the p-star vertical coordinate and
    WOA23-derived tracer fields for a global MPAS mesh, writing a
    model-neutral intermediate product that the downstream
    :py:class:`.InitialStateStep` can consume.

    This is a concrete subclass of
    :py:class:`polaris.ocean.vertical.pstar_init.PStarInitStep`.
    :py:meth:`init_tracers` interpolates conservative temperature and
    absolute salinity from the pre-remapped WOA23 product
    (``woa23_on_mesh.nc``) vertically to the current p-star midpoints at
    each fixed-point iteration.

    Attributes
    ----------
    remap_woa23_step : polaris.Step
        Upstream step that produces ``woa23_on_mesh.nc``.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        Upstream step that produces the culled ocean mesh.

    cull_topo_step : polaris.Step
        Upstream step that produces ``topography_culled.nc`` with
        ``base_elevation`` on the culled mesh cells.

    _woa23_ds : xarray.Dataset or None
        Lazily loaded WOA23 dataset; set in :py:meth:`run` before the
        fixed-point iteration is invoked.
    """

    def __init__(
        self,
        component,
        subdir,
        remap_woa23_step,
        cull_mesh_step,
        cull_topo_step,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        remap_woa23_step : polaris.Step
            The step that produces ``woa23_on_mesh.nc``.

        cull_mesh_step : polaris.Step
            The step that produces ``culled_ocean_mesh.nc``.

        cull_topo_step : polaris.Step
            The step that produces ``topography_culled.nc``.
        """
        super().__init__(
            component=component,
            name='pstar_init',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.remap_woa23_step = remap_woa23_step
        self.cull_mesh_step = cull_mesh_step
        self.cull_topo_step = cull_topo_step
        self._woa23_ds = None
        self.add_output_file(
            'pstar_init.nc',
            validate_vars=['ZTildeMid', 'SpecVol', 'temperature', 'salinity'],
        )

    def setup(self):
        """
        Declare input files from upstream steps.
        """
        super().setup()
        self.add_input_file(
            filename='woa23_on_mesh.nc',
            work_dir_target=os.path.join(
                self.remap_woa23_step.path, 'woa23_on_mesh.nc'
            ),
        )
        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )
        self.add_input_file(
            filename='topography_culled.nc',
            work_dir_target=os.path.join(
                self.cull_topo_step.path, 'topography_culled.nc'
            ),
        )

    def run(self):
        """
        Run the coupled p-star and tracer initialization from WOA23
        hydrography, writing ``pstar_init.nc``.
        """
        self._woa23_ds = xr.open_dataset('woa23_on_mesh.nc')

        ds_mesh = xr.open_dataset('culled_mesh.nc')
        ds_topo = xr.open_dataset('topography_culled.nc')
        geom_z_bot = _geom_z_bot_from_topo(ds_topo)

        ds_out = self.run_pstar_init(ds_mesh, geom_z_bot)
        write_netcdf(ds_out, 'pstar_init.nc')

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Interpolate conservative temperature and absolute salinity from the
        pre-remapped WOA23 depth levels to the current p-star midpoints.

        The WOA23 depth coordinate is positive-downward (meters); p-star
        midpoints are negative (geometric-height convention).  This method
        treats p-star pseudo-heights as approximate geometric heights, which
        is sufficient for convergence of the outer fixed-point loop.

        Parameters
        ----------
        ds : xarray.Dataset
            Current p-star dataset including ``ZTildeMid``,
            ``minLevelCell``, and ``maxLevelCell``.

        Returns
        -------
        conservative_temperature : xarray.DataArray
            CT with dimensions ``(Time, nCells, nVertLevels)``.
        absolute_salinity : xarray.DataArray
            SA with dimensions ``(Time, nCells, nVertLevels)``.
        """
        assert self._woa23_ds is not None, (
            'init_tracers called before _woa23_ds was loaded'
        )
        woa = self._woa23_ds
        # Convert positive-downward depth to negative geometric heights.
        # WOA23 depth is already sorted surface to seafloor (0 -> 5500 m).
        woa_z = -woa['depth'].values
        woa_ct = woa['ct_an'].values
        woa_sa = woa['sa_an'].values
        if woa['ct_an'].dims[0] == 'depth':
            woa_ct = woa_ct.T  # ensure (nCells, nWoa23Levels)
            woa_sa = woa_sa.T

        z_tilde_mid = ds.ZTildeMid.values  # (1, nCells, nVertLevels)
        ncells = ds.sizes['nCells']
        nlevels = ds.sizes['nVertLevels']
        min_lev = ds.minLevelCell.values - 1  # 0-indexed
        max_lev = ds.maxLevelCell.values - 1

        ct_out = np.full((1, ncells, nlevels), np.nan)
        sa_out = np.full((1, ncells, nlevels), np.nan)

        _fill_tracer_columns(
            z_tilde_mid,
            woa_z,
            woa_ct,
            woa_sa,
            min_lev,
            max_lev,
            ct_out,
            sa_out,
        )

        ct = xr.DataArray(
            data=ct_out,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        sa = xr.DataArray(
            data=sa_out,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'absolute salinity',
                'units': 'g kg-1',
            },
        )
        return ct, sa


def _geom_z_bot_from_topo(ds_topo):
    """
    Extract the geometric seafloor height (negative, in meters) from the
    culled topography dataset.

    Parameters
    ----------
    ds_topo : xarray.Dataset
        Culled topography dataset containing ``base_elevation``.
        ``base_elevation`` is negative for ocean cells (elevation below
        sea level), so no sign flip is needed.

    Returns
    -------
    xarray.DataArray
        Geometric seafloor height with dimension ``nCells`` (negative).
    """
    geom_z_bot = ds_topo['base_elevation']
    geom_z_bot.attrs['long_name'] = 'seafloor geometric height'
    geom_z_bot.attrs['units'] = 'm'
    return geom_z_bot


# the number of cells whose tracers are interpolated at once, which keeps each
# work array to a few MB
_TRACER_CHUNK_CELLS = 10000


def _fill_tracer_columns(
    z_tilde_mid,
    woa_z,
    woa_ct,
    woa_sa,
    min_lev,
    max_lev,
    ct_out,
    sa_out,
):
    """
    Fill ``ct_out`` and ``sa_out`` by vertical interpolation of WOA23 data to
    p-star midpoints, between each cell's first and last valid level.

    The WOA23 depths are the same for every column, so the source interval
    holding each midpoint is found for a chunk of cells at a time.  The
    result is what :py:func:`numpy.interp` gives column by column, including
    the flat extrapolation above the shallowest and below the deepest WOA23
    level.

    Parameters
    ----------
    z_tilde_mid : numpy.ndarray
        Shape ``(1, nCells, nVertLevels)``.  P-star pseudo-heights
        (negative, m).
    woa_z : numpy.ndarray
        Shape ``(nWoa23Levels,)``.  WOA23 geometric heights, sorted from
        surface (0) to seafloor (most negative).
    woa_ct, woa_sa : numpy.ndarray
        Shape ``(nCells, nWoa23Levels)``.
    min_lev, max_lev : numpy.ndarray
        Shape ``(nCells,)``.  0-indexed first and last valid level.
    ct_out, sa_out : numpy.ndarray
        Pre-allocated ``(1, nCells, nVertLevels)`` output arrays.
    """
    # source heights increasing upward, as interpolation needs
    z_src = np.asarray(woa_z[::-1], dtype=float)
    nsrc = z_src.size
    ncells, nlevels = z_tilde_mid.shape[1:]
    levels = np.arange(nlevels)
    for start in range(0, ncells, _TRACER_CHUNK_CELLS):
        cells = slice(start, min(start + _TRACER_CHUNK_CELLS, ncells))
        valid = (levels >= min_lev[cells, np.newaxis]) & (
            levels <= max_lev[cells, np.newaxis]
        )
        # only the valid levels, flattened, and the cell each belongs to
        cell, _ = np.nonzero(valid)
        z = z_tilde_mid[0, cells, :][valid]
        # the source interval holding each height, shared by both tracers
        index = np.clip(
            np.searchsorted(z_src, z, side='right') - 1, 0, nsrc - 2
        )
        dz_src = z_src[index + 1] - z_src[index]
        dz = z - z_src[index]
        below = z < z_src[0]
        above = z >= z_src[-1]
        first = cell * nsrc
        for woa, out in [(woa_ct, ct_out), (woa_sa, sa_out)]:
            values = np.ascontiguousarray(woa[cells, ::-1], dtype=float)
            values = values.ravel()
            lower = values[first + index]
            upper = values[first + index + 1]
            # the same arithmetic as numpy.interp, so the results match it
            # exactly, held at the end values beyond the source heights
            result = (upper - lower) / dz_src * dz + lower
            result = np.where(below, values[first], result)
            result = np.where(above, values[first + nsrc - 1], result)
            out_cells = out[0, cells, :]
            out_cells[valid] = result
