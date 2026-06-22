import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.vertical.pstar_init import PStarInitStep


class RealisticPStarInitStep(PStarInitStep):
    """
    A step that jointly initialises the p-star vertical coordinate and
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
        Run the coupled p-star and tracer initialisation from WOA23
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

        The WOA23 depth coordinate is positive-downward (metres); p-star
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
    Extract the geometric seafloor height (negative, in metres) from the
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
    Fill ``ct_out`` and ``sa_out`` by per-cell vertical interpolation of
    WOA23 data to p-star midpoints.

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
    ncells = z_tilde_mid.shape[1]
    for icell in range(ncells):
        lo = min_lev[icell]
        hi = max_lev[icell]
        z_mid = z_tilde_mid[0, icell, lo : hi + 1]
        ct_col = woa_ct[icell, :]
        sa_col = woa_sa[icell, :]
        ct_out[0, icell, lo : hi + 1] = np.interp(
            z_mid,
            woa_z[::-1],
            ct_col[::-1],
            left=ct_col[-1],
            right=ct_col[0],
        )
        sa_out[0, icell, lo : hi + 1] = np.interp(
            z_mid,
            woa_z[::-1],
            sa_col[::-1],
            left=sa_col[-1],
            right=sa_col[0],
        )
