import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.eos import compute_specvol
from polaris.ocean.vertical.grid_1d import generate_1d_grid
from polaris.ocean.vertical.pstar_init import PStarInitStep
from polaris.ocean.vertical.ztilde import (
    Gravity,
    RhoSw,
    pressure_from_z_tilde,
)


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

        geom_z_bot = self._clamp_to_representable_depth(ds_mesh, geom_z_bot)

        ds_out = self.run_pstar_init(ds_mesh, geom_z_bot)
        write_netcdf(ds_out, 'pstar_init.nc')

    def _clamp_to_representable_depth(self, ds_mesh, geom_z_bot):
        """
        Clamp the target seafloor ``geom_z_bot`` into the geometric depth range
        the p-star reference grid can actually represent, so the downstream
        :py:meth:`run_pstar_init` fixed-point iteration converges to a resting
        state (``ssh = 0``) instead of leaving a residual sea-surface height in
        cells whose bathymetry is deeper than the grid (or too shallow to form
        a valid column).

        The maximum representable geometric column depth ``D_max`` is the
        geometric thickness of a fully saturated column (pseudo-thicknesses
        equal to the full reference grid), computed once here by reusing the
        inherited :py:meth:`_build_pstar_coord_ds` and this step's
        :py:meth:`init_tracers`.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Horizontal mesh dataset.

        geom_z_bot : xarray.DataArray
            Target geometric seafloor height (negative, m) with dimension
            ``nCells``.

        Returns
        -------
        xarray.DataArray
            ``geom_z_bot`` clamped into the representable range.
        """
        config = self.config

        interfaces = generate_1d_grid(config=config)
        max_ref_pseudo_depth = float(interfaces[-1])
        p_max = RhoSw * Gravity * max_ref_pseudo_depth

        ncells = ds_mesh.sizes['nCells']
        surface_pressure = xr.DataArray(
            data=np.zeros(ncells, dtype=float), dims=['nCells']
        )
        bottom_pressure = xr.full_like(surface_pressure, p_max)

        ds_sat = self._build_pstar_coord_ds(
            ds_mesh, bottom_pressure, surface_pressure
        )
        ct, sa = self.init_tracers(ds_sat)
        p_mid = pressure_from_z_tilde(ds_sat.ZTildeMid)
        spec_vol = compute_specvol(
            config=config, temperature=ct, salinity=sa, pressure=p_mid
        )

        min_bottom_depth = config.getfloat('vertical_grid', 'min_bottom_depth')
        min_vert_levels = config.getint('vertical_grid', 'min_vert_levels')

        clamped = _clamp_geom_z_bot(
            geom_z_bot=geom_z_bot,
            spec_vol=spec_vol,
            pseudo_thickness=ds_sat.PseudoThickness,
            cell_mask=ds_sat.cellMask,
            min_bottom_depth=min_bottom_depth,
            min_vert_levels=min_vert_levels,
        )

        n_deep = int((clamped > geom_z_bot).sum())
        n_shallow = int((clamped < geom_z_bot).sum())
        self.logger.info(
            'Clamped geom_z_bot to the representable p-star column: '
            f'{n_deep} cells limited to the reference-grid depth, '
            f'{n_shallow} cells raised to the minimum depth.'
        )
        return clamped

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


def _clamp_geom_z_bot(
    geom_z_bot,
    spec_vol,
    pseudo_thickness,
    cell_mask,
    min_bottom_depth,
    min_vert_levels,
):
    """
    Clamp the target seafloor height into the representable geometric depth
    range ``[-D_max, -D_min]``.

    ``D_max`` is the geometric thickness of the (saturated) column described by
    ``spec_vol`` and ``pseudo_thickness``; ``D_min`` is the deeper of
    ``min_bottom_depth`` and the geometric depth needed to supply
    ``min_vert_levels`` layers (never deeper than ``D_max``).

    Parameters
    ----------
    geom_z_bot : xarray.DataArray
        Target geometric seafloor height (negative, m) with dimension
        ``nCells``.

    spec_vol : xarray.DataArray
        Specific volume of the saturated column
        (``(Time,) nCells, nVertLevels``).

    pseudo_thickness : xarray.DataArray
        Pseudo-thickness of the saturated column, same shape as ``spec_vol``.

    cell_mask : xarray.DataArray
        Boolean mask of valid layers (``nCells, nVertLevels``).

    min_bottom_depth : float
        Minimum geometric water-column depth (m).

    min_vert_levels : int
        Minimum number of layers a valid column must contain.

    Returns
    -------
    xarray.DataArray
        ``geom_z_bot`` clamped so that ``-D_max <= geom_z_bot <= -D_min``.
    """
    geom_thickness = (RhoSw * spec_vol * pseudo_thickness).where(
        cell_mask, 0.0
    )
    if 'Time' in geom_thickness.dims:
        geom_thickness = geom_thickness.isel(Time=0)

    d_max = geom_thickness.sum(dim='nVertLevels')
    depth_for_min_levels = geom_thickness.isel(
        nVertLevels=slice(0, min_vert_levels)
    ).sum(dim='nVertLevels')
    d_min = np.minimum(
        np.maximum(min_bottom_depth, depth_for_min_levels), d_max
    )

    clamped = np.minimum(np.maximum(geom_z_bot, -d_max), -d_min)
    clamped.attrs = dict(geom_z_bot.attrs)
    return clamped


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
