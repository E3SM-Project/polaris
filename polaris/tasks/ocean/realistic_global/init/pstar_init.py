import os

import gsw
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.cf import add_cf_conventions
from polaris.mesh.attrs import add_mesh_var_attrs
from polaris.ocean.eos import compute_specvol
from polaris.ocean.ice_shelf import (
    compute_freezing_temperature,
    compute_land_ice_pressure_from_thickness,
)
from polaris.ocean.vertical.bathymetry_holes import fill_max_level_holes
from polaris.ocean.vertical.grid_1d import generate_1d_grid
from polaris.ocean.vertical.pstar_init import PStarInitStep
from polaris.ocean.vertical.ztilde import (
    Gravity,
    RhoSw,
    pressure_from_z_tilde,
)
from polaris.tasks.ocean.realistic_global.cavities import (
    has_ice_shelf_cavities,
)


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

    With ice-shelf cavities, each column carries the land-ice load that
    MPAS-Ocean will apply, and a column the load would leave too thin is a
    thin film of fresh water at the freezing point (see
    :py:func:`compute_land_ice_load`).

    Attributes
    ----------
    remap_woa23_step : polaris.Step
        Upstream step that produces ``woa23_on_mesh.nc``.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        Upstream step that produces the culled ocean mesh.

    cull_topo_step : polaris.Step
        Upstream step that produces ``topography_culled.nc`` with
        ``ocean_masked_base_elevation`` on the culled mesh cells.

    _woa23_ds : xarray.Dataset or None
        Lazily loaded WOA23 dataset; set in :py:meth:`run` before the
        fixed-point iteration is invoked.

    _thin_film : xarray.Dataset or None
        With ice-shelf cavities, ``thinFilmMask`` and ``landIcePressure`` for
        :py:meth:`init_tracers`, set before each p-star solve
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
        self._thin_film = None
        self.add_output_file(
            'pstar_init.nc',
            validate_vars=['ZTildeMid', 'SpecVol', 'temperature', 'salinity'],
        )
        self.add_cf_check('pstar_init.nc')

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

        geom_z_bot = self._clamp_to_representable_depth(ds_mesh, geom_z_bot)

        land_ice_pressure = None
        if has_ice_shelf_cavities(self.config):
            land_ice_pressure = compute_land_ice_pressure_from_thickness(
                land_ice_thickness=ds_topo.ocean_masked_ice_thickness.fillna(
                    0.0
                ),
                modify_mask=ds_topo.landIceMask,
                land_ice_density=self.config.getfloat(
                    'realistic_global_cavities', 'land_ice_density'
                ),
            )

        ds_out = self._run_pstar_init_filling_holes(
            ds_mesh, geom_z_bot, land_ice_pressure
        )
        if land_ice_pressure is not None:
            ds_out = add_land_ice_fields(
                ds_out, ds_topo, land_ice_pressure, self._thin_film
            )
        ds_out = add_cf_conventions(add_mesh_var_attrs(ds_out))
        write_netcdf(ds_out, 'pstar_init.nc')

    def _clamp_to_representable_depth(self, ds_mesh, geom_z_bot):
        """
        Clamp the target seafloor ``geom_z_bot`` into the geometric depth range
        the p-star reference grid can actually represent, so the downstream
        :py:meth:`run_pstar_init` fixed-point iteration can make ``ssh`` match
        its prescribed value (0 here, because ``SurfacePressure = 0``) instead
        of leaving a residual sea-surface height in cells whose bathymetry is
        deeper than the grid (or too shallow to form a valid column).

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

    def _run_pstar_init_filling_holes(
        self, ds_mesh, geom_z_bot, land_ice_pressure=None
    ):
        """
        Run :py:meth:`run_pstar_init`, filling isolated bathymetry "holes"
        until none remain and, with ice-shelf cavities, until the land-ice
        load agrees with the number of layers in each column.

        A hole is an ocean cell whose converged ``maxLevelCell`` is deeper than
        that of every one of its horizontal ocean neighbors; its deepest layers
        have no neighbor at the same level to exchange with, so they are
        effectively inert.  MPAS-Ocean's init mode removes these by capping
        ``maxLevelCell`` at the deepest neighbor.  Here we do the equivalent as
        a bathymetry correction: after each p-star solve we cap each hole's
        seafloor at the converged geometric height of the bottom interface of
        its deepest-neighbor level, then re-solve.  Because the column is
        anchored at the prescribed sea surface, this only shortens the affected
        columns and ``ssh`` keeps matching its prescribed value.

        Holes are detected on the *converged* ``maxLevelCell`` (the equation of
        state can nudge a neighbor's level by one relative to any pre-iteration
        estimate), and capping only ever reduces ``maxLevelCell``, so the loop
        is monotone and should terminate.  Holes that remain after a fixed
        number of passes are an error rather than something to write out.

        Under land ice, the load MPAS-Ocean applies depends on the number of
        layers in the column, which the p-star solve determines (see
        :py:func:`compute_land_ice_load`).  The first solve assumes no thin
        film, and each later one takes its layers from the solve before, until
        neither the layers of the thin film nor the holes change.  The first
        solve takes its layers from the reference grid, down to the seafloor.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Horizontal mesh dataset (provides ``cellsOnCell`` and
            ``nEdgesOnCell``).

        geom_z_bot : xarray.DataArray
            Target geometric seafloor height (negative, m) with dimension
            ``nCells``, already clamped to the representable range.

        land_ice_pressure : xarray.DataArray, optional
            The pressure (Pa) of the land ice on the ocean, with dimension
            ``nCells``, or ``None`` without ice-shelf cavities

        Returns
        -------
        xarray.Dataset
            The converged p-star init dataset with holes filled.
        """
        cells_on_cell = ds_mesh.cellsOnCell.values - 1
        n_edges_on_cell = ds_mesh.nEdgesOnCell.values
        max_passes = 20

        level_count = None
        if land_ice_pressure is not None:
            level_count = estimate_level_count(
                interfaces=generate_1d_grid(config=self.config),
                bottom_depth=-geom_z_bot.values,
                min_vert_levels=self.config.getint(
                    'vertical_grid', 'min_vert_levels'
                ),
            )
        ds_out = self._run_pstar_init_with_load(
            ds_mesh, geom_z_bot, land_ice_pressure, level_count
        )
        for outer in range(max_passes):
            max_level_cell = ds_out.maxLevelCell.values
            filled = fill_max_level_holes(
                max_level_cell=max_level_cell,
                cells_on_cell=cells_on_cell,
                n_edges_on_cell=n_edges_on_cell,
            )
            is_filled = filled < max_level_cell
            n_filled = int(is_filled.sum())

            n_relayered = 0
            n_moved = 0
            if land_ice_pressure is not None:
                min_level_cell = ds_out.minLevelCell.values
                new_level_count = max_level_cell - min_level_cell + 1
                assert self._thin_film is not None
                film = self._thin_film.thinFilmMask.values == 1
                n_relayered = int(
                    (film & (new_level_count != level_count)).sum()
                )
                level_count = new_level_count

                # the p-star solve moves the seafloor to where a partial
                # bottom cell is representable.  Under a load, the sea
                # surface does not move with it, so the load and SSH must be
                # computed again from the seafloor the column actually has.
                moved = _loaded_columns_with_moved_seafloor(ds_out, geom_z_bot)
                n_moved = int(moved.sum())
                geom_z_bot = xr.where(
                    xr.DataArray(moved, dims=['nCells']),
                    -_squeeze_time(ds_out.bottomDepth),
                    geom_z_bot,
                )

            if n_filled == 0 and n_relayered == 0 and n_moved == 0:
                if outer > 0:
                    self.logger.info(
                        f'No bathymetry holes remain and the thin film is '
                        f'consistent after {outer} pass(es).'
                    )
                return ds_out

            # converged geometric height of the bottom interface of the capped
            # level (0-based interface index == 1-based capped level)
            new_geom_z_bot = ds_out.GeomZInterface.isel(
                Time=0,
                nVertLevelsP1=xr.DataArray(filled, dims='nCells'),
            )
            if land_ice_pressure is not None and n_filled > 0:
                # under land ice, the layers are squashed, so their bottom
                # interface is not where the column must end to lose them
                new_geom_z_bot = xr.where(
                    _squeeze_time(ds_out.SurfacePressure) > 0.0,
                    shorten_loaded_columns(
                        geom_z_bot=geom_z_bot,
                        bottom_pressure=_squeeze_time(ds_out.BottomPressure),
                        spec_vol=_squeeze_time(ds_out.SpecVol),
                        max_level_cell=max_level_cell,
                        interfaces=generate_1d_grid(config=self.config),
                        filled=filled,
                    ),
                    new_geom_z_bot,
                )
            geom_z_bot = xr.where(
                xr.DataArray(is_filled, dims=['nCells']),
                new_geom_z_bot,
                geom_z_bot,
            )
            geom_z_bot.attrs['long_name'] = 'seafloor geometric height'
            geom_z_bot.attrs['units'] = 'm'

            self.logger.info(
                f'Bathymetry-hole pass {outer}: capping {n_filled} holes at '
                f'the deepest ocean neighbor, updating the thin film in '
                f'{n_relayered} cells and the land-ice load in {n_moved} '
                f'cells whose seafloor moved, then re-running p-star init.'
            )
            ds_out = self._run_pstar_init_with_load(
                ds_mesh, geom_z_bot, land_ice_pressure, level_count
            )

        raise ValueError(
            f'Bathymetry holes or thin-film layers still change after '
            f'{max_passes} passes.  The initial condition would keep cells '
            f'deeper than all of their neighbors, or a thin film inconsistent '
            f'with its layers, so it is not written.'
        )

    def _run_pstar_init_with_load(
        self, ds_mesh, geom_z_bot, land_ice_pressure, level_count
    ):
        """
        Run :py:meth:`run_pstar_init`, with the land-ice load MPAS-Ocean will
        apply when there are ice-shelf cavities.
        """
        if land_ice_pressure is None:
            return self.run_pstar_init(ds_mesh, geom_z_bot)

        section = self.config['realistic_global_cavities']
        surface_pressure, ssh, thin_film_mask = compute_land_ice_load(
            land_ice_pressure=land_ice_pressure,
            geom_z_bot=geom_z_bot,
            level_count=level_count,
            thin_film_layer_thickness=section.getfloat(
                'thin_film_layer_thickness'
            ),
            draft_density=section.getfloat('land_ice_draft_density'),
        )
        self._thin_film = xr.Dataset(
            {
                'thinFilmMask': thin_film_mask.astype(int),
                'landIcePressure': land_ice_pressure,
            }
        )
        return self.run_pstar_init(
            ds_mesh,
            geom_z_bot,
            surface_pressure=surface_pressure,
            sea_surface_height=ssh,
        )

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
        if self._thin_film is not None:
            ct, sa = fill_thin_film_tracers(
                self.config,
                ct,
                sa,
                self._thin_film.thinFilmMask,
                self._thin_film.landIcePressure,
            )
        return ct, sa


def shorten_loaded_columns(
    geom_z_bot, bottom_pressure, spec_vol, max_level_cell, interfaces, filled
):
    """
    Raise the seafloor of columns under a surface load so that their deepest
    layer becomes ``filled``.

    A column's layers come from its bottom pressure, which counts the load,
    while its layers are squashed under the load, so the bottom interface of
    layer ``filled`` lies far above where the column must end.  Instead, the
    column is shortened by the pseudo-depth of its bottom pressure below the
    reference depth of that interface, less 1% of the layer, converted to a
    geometric length with the specific volume of the deepest layer.

    Parameters
    ----------
    geom_z_bot : xarray.DataArray
        The geometric height (m, negative) of the seafloor, with dimension
        ``nCells``

    bottom_pressure : xarray.DataArray
        The bottom pressure (Pa) of each column, with dimension ``nCells``

    spec_vol : xarray.DataArray
        The specific volume (m3 kg-1), with dimensions ``nCells`` and
        ``nVertLevels``

    max_level_cell : numpy.ndarray
        The 1-based deepest layer of each column

    interfaces : numpy.ndarray
        The reference depths (m, positive down) of the layer interfaces

    filled : numpy.ndarray
        The 1-based deepest layer each column should have

    Returns
    -------
    xarray.DataArray
        The raised seafloor height
    """
    interfaces = np.asarray(interfaces)
    filled = np.asarray(filled)
    target = interfaces[filled] - 0.01 * (
        interfaces[filled] - interfaces[filled - 1]
    )
    pseudo_bottom = bottom_pressure.values / (RhoSw * Gravity)
    excess = np.maximum(pseudo_bottom - target, 0.0)
    cells = np.arange(len(filled))
    bottom_spec_vol = spec_vol.values[cells, np.asarray(max_level_cell) - 1]
    raised = geom_z_bot.values + excess * RhoSw * bottom_spec_vol
    return xr.DataArray(raised, dims=geom_z_bot.dims)


def _loaded_columns_with_moved_seafloor(ds_out, geom_z_bot, tolerance=1e-6):
    """
    Find the columns under a surface load whose seafloor the p-star solve
    left more than ``tolerance`` (m) from its target
    """
    loaded = _squeeze_time(ds_out.SurfacePressure).values > 0.0
    bottom_depth = _squeeze_time(ds_out.bottomDepth).values
    return loaded & (np.abs(bottom_depth + geom_z_bot.values) > tolerance)


def _squeeze_time(da):
    """
    Drop the ``Time`` dimension of a data array, if it has one
    """
    if 'Time' in da.dims:
        da = da.isel(Time=0)
    return da


def estimate_level_count(interfaces, bottom_depth, min_vert_levels):
    """
    Estimate the number of active layers in each column from the reference
    grid: the layers whose tops lie above the seafloor.

    Parameters
    ----------
    interfaces : numpy.ndarray
        The reference depths (m, positive down) of the layer interfaces,
        starting at 0

    bottom_depth : numpy.ndarray
        The depth (m, positive down) of the seafloor in each column

    min_vert_levels : int
        The minimum number of layers in a column

    Returns
    -------
    level_count : numpy.ndarray
        The estimated number of active layers in each column
    """
    tops = np.asarray(interfaces)[:-1]
    count = np.sum(tops[np.newaxis, :] < bottom_depth[:, np.newaxis], axis=1)
    return np.clip(count, min_vert_levels, len(tops))


def compute_land_ice_load(
    land_ice_pressure,
    geom_z_bot,
    level_count,
    thin_film_layer_thickness,
    draft_density,
):
    """
    Compute the land-ice load on each column that MPAS-Ocean will apply, and
    the sea-surface height that follows from it.

    MPAS-Ocean caps the land-ice pressure at the pressure under which ice
    would float on a thin film: :math:`N h_{min}` thick for a column of
    :math:`N` active layers, each at its wetting-and-drying minimum
    thickness :math:`h_{min}`.  Where the ice is lighter than that, the
    sea-surface height is the draft of floating ice; elsewhere, the column is
    a thin film.

    Parameters
    ----------
    land_ice_pressure : xarray.DataArray
        The pressure (Pa) of the land ice on the ocean, with dimension
        ``nCells``

    geom_z_bot : xarray.DataArray
        The geometric height (m, negative) of the seafloor, with dimension
        ``nCells``

    level_count : numpy.ndarray
        The number of active layers in each column

    thin_film_layer_thickness : float
        The thickness (m) of each active layer of a thin film

    draft_density : float
        The ocean density (kg m-3) that converts between pressure and the
        draft of floating ice

    Returns
    -------
    surface_pressure : xarray.DataArray
        The land-ice load (Pa) that MPAS-Ocean applies

    ssh : xarray.DataArray
        The sea-surface height (m) under that load

    thin_film_mask : xarray.DataArray
        Where the load is capped, so the column is a thin film
    """
    bottom_depth = -geom_z_bot
    film_thickness = thin_film_layer_thickness * xr.DataArray(
        level_count, dims=bottom_depth.dims
    )
    max_pressure = draft_density * Gravity * (bottom_depth - film_thickness)
    max_pressure = np.maximum(max_pressure, 0.0)
    thin_film_mask = land_ice_pressure > max_pressure
    surface_pressure = np.minimum(land_ice_pressure, max_pressure)
    surface_pressure.attrs = {
        'long_name': 'land-ice pressure applied to the ocean',
        'units': 'Pa',
    }
    ssh = -surface_pressure / (draft_density * Gravity)
    ssh.attrs = {'long_name': 'sea surface geometric height', 'units': 'm'}
    return surface_pressure, ssh, thin_film_mask


def fill_thin_film_tracers(config, ct, sa, thin_film_mask, land_ice_pressure):
    """
    Fill the layers of a thin film with fresh water at its freezing point, as
    in the ISOMIP+ tasks.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with ``ocean`` and ``ice_shelf_freeze`` sections

    ct : xarray.DataArray
        Conservative temperature, with dimensions ``Time``, ``nCells`` and
        ``nVertLevels``

    sa : xarray.DataArray
        Absolute salinity, with the same dimensions

    thin_film_mask : xarray.DataArray
        1 in thin-film columns and 0 elsewhere, with dimension ``nCells``

    land_ice_pressure : xarray.DataArray
        The pressure (Pa) of the land ice on the ocean, at which the film
        freezes

    Returns
    -------
    ct : xarray.DataArray
        Conservative temperature, at the freezing point in the thin film

    sa : xarray.DataArray
        Absolute salinity, zero in the thin film
    """
    film = thin_film_mask == 1
    # the ocean model's freezing point is a potential temperature, which at
    # zero salinity gsw converts to conservative temperature
    freezing_pt = compute_freezing_temperature(
        config=config,
        salinity=xr.zeros_like(land_ice_pressure),
        pressure=land_ice_pressure,
    )
    freezing_ct = xr.DataArray(
        gsw.CT_from_pt(0.0, freezing_pt.values), dims=freezing_pt.dims
    )
    ct_film = xr.where(film, freezing_ct, ct).transpose(*ct.dims)
    sa_film = xr.where(film, 0.0, sa).transpose(*sa.dims)
    # keep the tracers undefined below the seafloor
    ct_film = ct_film.where(ct.notnull())
    sa_film = sa_film.where(sa.notnull())
    ct_film.attrs = ct.attrs
    sa_film.attrs = sa.attrs
    return ct_film, sa_film


def add_land_ice_fields(ds_out, ds_topo, land_ice_pressure, thin_film):
    """
    Add the land-ice fields MPAS-Ocean reads from its initial state.

    Parameters
    ----------
    ds_out : xarray.Dataset
        The p-star initial condition, with ``ssh``

    ds_topo : xarray.Dataset
        The culled topography, with ``landIceMask``, and
        ``ocean_masked_ice_frac`` and ``ocean_masked_grounded_frac``, the
        fractions of the ocean part of each cell under land ice and under
        grounded ice

    land_ice_pressure : xarray.DataArray
        The full pressure (Pa) of the land ice, before MPAS-Ocean caps it

    thin_film : xarray.Dataset
        ``thinFilmMask`` from the last p-star solve

    Returns
    -------
    ds_out : xarray.Dataset
        The initial condition with the land-ice fields added
    """
    land_ice_mask = ds_topo.landIceMask == 1
    ice_frac = ds_topo.ocean_masked_ice_frac
    grounded_frac = ds_topo.ocean_masked_grounded_frac
    land_ice_fraction = ice_frac.where(land_ice_mask, 0.0)
    floating_fraction = np.maximum(ice_frac - grounded_frac, 0.0).where(
        land_ice_mask, 0.0
    )
    floating_mask = land_ice_mask & (floating_fraction > 0.0)

    ssh = ds_out.ssh
    if 'Time' in ssh.dims:
        ssh = ssh.isel(Time=0)

    fields = {
        'landIceMask': (land_ice_mask.astype(int), None),
        'landIceFloatingMask': (floating_mask.astype(int), None),
        'landIceFraction': (land_ice_fraction, '1'),
        'landIceFloatingFraction': (floating_fraction, '1'),
        'landIcePressure': (land_ice_pressure, 'Pa'),
        'landIceDraft': (ssh, 'm'),
        'thinFilmMask': (thin_film.thinFilmMask, None),
    }
    long_names = {
        'landIceMask': 'cells covered by land ice (1) or not (0)',
        'landIceFloatingMask': 'cells covered by floating land ice (1) or '
        'not (0)',
        'landIceFraction': 'fraction of the cell covered by land ice',
        'landIceFloatingFraction': 'fraction of the cell covered by '
        'floating land ice',
        'landIcePressure': 'pressure of the land ice on the ocean',
        'landIceDraft': 'elevation of the base of the land ice',
        'thinFilmMask': 'cells holding a thin film under land ice (1) or '
        'not (0)',
    }
    for name, (field, units) in fields.items():
        da = xr.DataArray(field.values, dims=('nCells',))
        attrs = {'long_name': long_names[name]}
        if units is not None:
            attrs['units'] = units
        da.attrs = attrs
        ds_out[name] = da.expand_dims(dim='Time', axis=0)
    return ds_out


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
    Extract the geometric seafloor height (negative, in meters) from the
    culled topography dataset.

    The seafloor is the mean base elevation over the ocean part of each cell,
    ``ocean_masked_base_elevation``, which is below sea level.  The mean over
    the whole cell would include any land in the cell, and can be above sea
    level where the cell holds steep land or ice-covered topography.  A cell
    the cull keeps with no ocean in it at all, such as one in a critical
    passage, has no such mean and takes sea level, which
    :py:meth:`RealisticPStarInitStep._clamp_to_representable_depth` then
    deepens to the minimum depth.

    Parameters
    ----------
    ds_topo : xarray.Dataset
        Culled topography dataset containing ``ocean_masked_base_elevation``,
        which is negative (below sea level), so no sign flip is needed.

    Returns
    -------
    xarray.DataArray
        Geometric seafloor height with dimension ``nCells`` (negative).
    """
    geom_z_bot = ds_topo['ocean_masked_base_elevation'].fillna(0.0)
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
