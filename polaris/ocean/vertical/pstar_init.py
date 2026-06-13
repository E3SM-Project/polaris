"""
Base class for steps that initialize the p-star vertical coordinate by
iterating on BottomPressure until the recovered geometric seafloor depth
matches a target bathymetry within a configurable tolerance.
"""

from abc import ABC, abstractmethod

import numpy as np
import xarray as xr

from polaris.ocean.eos import compute_specvol
from polaris.ocean.vertical.grid_1d import generate_1d_grid
from polaris.ocean.vertical.pstar import init_pstar_vertical_coord
from polaris.ocean.vertical.ztilde import (
    Gravity,
    RhoSw,
    geom_height_from_pseudo_height,
    pressure_from_z_tilde,
)
from polaris.step import Step


class PStarInitStep(Step, ABC):
    """
    Base class for initialization steps that use the p-star vertical
    coordinate.

    Subclasses must implement :py:meth:`init_tracers`.  Subclasses may
    optionally override :py:meth:`_build_pstar_coord_ds` when per-cell
    coordinate construction is required (e.g. when each cell has a different
    reference pseudo-depth).

    The outer fixed-point iteration is provided by
    :py:meth:`run_pstar_init`.
    """

    @abstractmethod
    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Initialize conservative temperature (CT) and absolute salinity (SA)
        at p-star layer midpoints for the current outer iteration.

        Parameters
        ----------
        ds : xarray.Dataset
            Current p-star dataset, including ``ZTildeMid``,
            ``ZTildeInterface``, ``PseudoThickness``, ``cellMask``,
            ``minLevelCell``, and ``maxLevelCell``.

        Returns
        -------
        conservative_temperature : xarray.DataArray
            CT with dimensions ``(Time, nCells, nVertLevels)``.
        absolute_salinity : xarray.DataArray
            SA with dimensions ``(Time, nCells, nVertLevels)``.
        """

    def _build_pstar_coord_ds(
        self,
        ds_mesh: xr.Dataset,
        bottom_pressure: xr.DataArray,
        surface_pressure: xr.DataArray | None = None,
    ) -> xr.Dataset:
        """
        Build the p-star vertical coordinate dataset for one outer iteration.

        The default implementation calls
        :py:func:`~polaris.ocean.vertical.pstar.init_pstar_vertical_coord`
        once on the full mesh.  Subclasses may override this method when
        per-cell coordinate construction is required.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Horizontal mesh dataset.
        bottom_pressure : xarray.DataArray
            Current BottomPressure guess with dimension ``nCells`` (Pa).
        surface_pressure : xarray.DataArray, optional
            Sea-surface pressure with dimension ``nCells`` (Pa).  Defaults to
            zero for all cells.

        Returns
        -------
        xarray.Dataset
            Dataset with p-star coordinate variables added.
        """
        config = self.config
        ds = ds_mesh.copy()
        ds['BottomPressure'] = bottom_pressure
        ds.BottomPressure.attrs['long_name'] = 'seafloor pressure'
        ds.BottomPressure.attrs['units'] = 'Pa'
        if surface_pressure is None:
            surface_pressure = xr.zeros_like(bottom_pressure)
        ds['SurfacePressure'] = surface_pressure
        ds.SurfacePressure.attrs['long_name'] = 'sea surface pressure'
        ds.SurfacePressure.attrs['units'] = 'Pa'
        init_pstar_vertical_coord(config, ds)
        if 'vertCoordMovementWeights' not in ds:
            ds['vertCoordMovementWeights'] = xr.DataArray(
                data=np.ones(ds.sizes['nVertLevels'], dtype=float),
                dims=['nVertLevels'],
                attrs={
                    'long_name': 'vertical coordinate movement weights',
                    'units': '1',
                },
            )
        return ds

    def run_pstar_init(
        self,
        ds_mesh: xr.Dataset,
        geom_z_bot: xr.DataArray,
        surface_pressure: xr.DataArray | None = None,
        sea_surface_height: xr.DataArray | None = None,
    ) -> xr.Dataset:
        """
        Run the fixed-point iteration that determines BottomPressure (and
        therefore the p-star coordinate) such that the recovered geometric
        water-column thickness matches the target within a configurable
        fractional tolerance.

        At convergence the returned dataset contains all p-star coordinate
        variables, converged tracer fields, specific volume, pressure,
        geometric height at layer midpoints and interfaces, ``bottomDepth``
        set to the actual converged geometric water-column thickness, and
        ``ssh`` computed as the diagnostic geometric sea-surface height.

        Parameters
        ----------
        ds_mesh : xarray.Dataset
            Horizontal mesh dataset.
        geom_z_bot : xarray.DataArray
            Target geometric height of the seafloor (negative, in metres)
            with dimension ``nCells``.  Used both to anchor
            ``geom_height_from_pseudo_height`` and to set the target
            water-column thickness.
        surface_pressure : xarray.DataArray, optional
            Sea-surface pressure (Pa) with dimension ``nCells``.  Defaults
            to zero for all cells.
        sea_surface_height : xarray.DataArray, optional
            Prescribed sea-surface height (m) with dimension ``nCells``.
            The target water-column thickness is ``sea_surface_height -
            geom_z_bot``; the iteration adjusts ``BottomPressure`` until
            this target is met, so the converged ``ssh`` equals this value.
            Defaults to ``-surface_pressure / (RhoSw * Gravity)``, i.e. the
            resting surface-pressure depression for a reference-density fluid.

        Returns
        -------
        xarray.Dataset
            Dataset containing all base-class output variables with
            ``long_name`` and ``units`` attributes set.
        """
        logger = self.logger
        config = self.config

        ncells = ds_mesh.sizes['nCells']

        if surface_pressure is None:
            surface_pressure = xr.DataArray(
                data=np.zeros(ncells, dtype=float),
                dims=['nCells'],
                attrs={
                    'long_name': 'sea surface pressure',
                    'units': 'Pa',
                },
            )

        if sea_surface_height is None:
            sea_surface_height = -surface_pressure / (RhoSw * Gravity)

        goal_geom_water_column_thickness = sea_surface_height - geom_z_bot

        bottom_pressure = (
            surface_pressure
            + RhoSw * Gravity * goal_geom_water_column_thickness
        )

        pseudothickness_iter_count = config.getint(
            'vertical_grid', 'pseudothickness_iter_count'
        )
        water_col_adjust_frac_change_threshold = config.getfloat(
            'vertical_grid', 'water_col_adjust_frac_change_threshold'
        )
        if water_col_adjust_frac_change_threshold < 0.0:
            raise ValueError(
                '"water_col_adjust_frac_change_threshold" must be nonnegative.'
            )

        prev_geom_water_column_thickness: xr.DataArray | None = None
        prev_adjusted_bottom_pressure: xr.DataArray | None = None

        # Derive nVertLevels from the config-driven reference grid so the
        # fallback zero-arrays below are shaped correctly even when ds_mesh
        # does not carry a nVertLevels dimension.
        nvertlevels = len(generate_1d_grid(config)) - 1

        # These are assigned inside the loop; initialise to satisfy type
        # checkers and so the post-loop assembly can reference them even if
        # the loop body executes zero times (pseudothickness_iter_count == 0).
        ds: xr.Dataset = ds_mesh.copy()
        ct: xr.DataArray = xr.DataArray(
            data=np.zeros((1, ncells, nvertlevels), dtype=float),
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        sa = ct.copy()
        p_mid = ct.copy()
        spec_vol = ct.copy()
        geom_z_inter: xr.DataArray = xr.DataArray(
            data=np.zeros((1, ncells, nvertlevels + 1), dtype=float),
            dims=['Time', 'nCells', 'nVertLevelsP1'],
        )
        geom_z_mid = ct.copy()
        geom_water_column_thickness: xr.DataArray = (
            goal_geom_water_column_thickness.copy()
        )

        for iteration in range(pseudothickness_iter_count):
            ds = self._build_pstar_coord_ds(
                ds_mesh, bottom_pressure, surface_pressure
            )
            # ds.BottomPressure is the post-partial-cell-snap value
            adjusted_bottom_pressure = ds.BottomPressure

            ct, sa = self.init_tracers(ds)
            p_mid = pressure_from_z_tilde(ds.ZTildeMid)

            logger.debug(f'Iteration {iteration}: p_mid = {p_mid}')

            spec_vol = compute_specvol(
                config=config,
                temperature=ct,
                salinity=sa,
                pressure=p_mid,
            )
            assert isinstance(spec_vol, xr.DataArray)

            min_level_cell = ds.minLevelCell - 1
            max_level_cell = ds.maxLevelCell - 1

            geom_z_inter, geom_z_mid = geom_height_from_pseudo_height(
                geom_z_bot=geom_z_bot,
                h_tilde=ds.PseudoThickness,
                spec_vol=spec_vol,
                min_level_cell=min_level_cell,
                max_level_cell=max_level_cell,
            )

            geom_z_min = geom_z_inter.isel(
                Time=0, nVertLevelsP1=min_level_cell
            )
            geom_z_max = geom_z_inter.isel(
                Time=0, nVertLevelsP1=max_level_cell + 1
            )
            geom_water_column_thickness = geom_z_min - geom_z_max

            # convergence check
            if prev_geom_water_column_thickness is not None:
                frac_change = (
                    np.abs(
                        geom_water_column_thickness
                        - prev_geom_water_column_thickness
                    )
                    / prev_geom_water_column_thickness
                )
                max_frac_change = frac_change.max().item()

                logger.info(
                    f'Iteration {iteration}: max fractional change in '
                    'geometric water-column thickness = '
                    f'{max_frac_change:.6e}'
                )

                if max_frac_change < water_col_adjust_frac_change_threshold:
                    logger.info(
                        f'Early stopping after iteration {iteration}: '
                        f'max fractional change ({max_frac_change:.6e}) '
                        'is below threshold '
                        f'({water_col_adjust_frac_change_threshold:.6e}).'
                    )
                    break

            # full-cell stagnation check — convergence check above takes
            # priority so that a perfect initial guess (scaling = 1) exits
            # cleanly rather than triggering this warning.
            if (
                prev_adjusted_bottom_pressure is not None
                and (
                    adjusted_bottom_pressure == prev_adjusted_bottom_pressure
                ).all()
            ):
                logger.warning(
                    f'Iteration {iteration}: full-cell snap is holding '
                    'BottomPressure constant — stopping early to avoid '
                    'non-convergence. bottomDepth will reflect the actual '
                    'cell bottom rather than the target bathymetry.'
                )
                break

            # proportional-ratio update
            scaling_factor = (
                goal_geom_water_column_thickness / geom_water_column_thickness
            )
            logger.info(
                f'Iteration {iteration}: '
                f'min scaling factor = {scaling_factor.min().item():.6f}, '
                f'max scaling factor = {scaling_factor.max().item():.6f}'
            )

            bottom_pressure = (
                surface_pressure
                + (adjusted_bottom_pressure - surface_pressure)
                * scaling_factor
            )

            prev_adjusted_bottom_pressure = adjusted_bottom_pressure
            prev_geom_water_column_thickness = geom_water_column_thickness

        # Assemble the output dataset from the converged state
        ds['temperature'] = ct
        ds.temperature.attrs['long_name'] = 'conservative temperature'
        ds.temperature.attrs['units'] = 'degC'

        ds['salinity'] = sa
        ds.salinity.attrs['long_name'] = 'absolute salinity'
        ds.salinity.attrs['units'] = 'g kg-1'

        ds['SpecVol'] = spec_vol
        ds.SpecVol.attrs['long_name'] = 'specific volume'
        ds.SpecVol.attrs['units'] = 'm3 kg-1'

        ds['pressure'] = p_mid
        ds.pressure.attrs['long_name'] = 'pressure at layer midpoints'
        ds.pressure.attrs['units'] = 'Pa'

        ds['GeomZMid'] = geom_z_mid
        ds.GeomZMid.attrs['long_name'] = 'geometric height at layer midpoints'
        ds.GeomZMid.attrs['units'] = 'm'

        ds['GeomZInterface'] = geom_z_inter
        ds.GeomZInterface.attrs['long_name'] = (
            'geometric height at layer interfaces'
        )
        ds.GeomZInterface.attrs['units'] = 'm'

        # Use the actual converged water-column thickness (not the target)
        # for thermodynamic self-consistency, even when bottom-cell snapping
        # prevents an exact match to the target bathymetry.
        ds['bottomDepth'] = geom_water_column_thickness
        ds.bottomDepth.attrs['long_name'] = 'seafloor geometric depth'
        ds.bottomDepth.attrs['units'] = 'm'

        ds['ssh'] = geom_z_min
        ds.ssh.attrs['long_name'] = 'sea surface geometric height'
        ds.ssh.attrs['units'] = 'm'

        ds.ZTildeMid.attrs['long_name'] = 'pseudo-height at layer midpoints'
        ds.ZTildeMid.attrs['units'] = 'm'

        ds.ZTildeInterface.attrs['long_name'] = (
            'pseudo-height at layer interfaces'
        )
        ds.ZTildeInterface.attrs['units'] = 'm'

        ds.PseudoThickness.attrs['long_name'] = 'pseudo-layer thickness'
        ds.PseudoThickness.attrs['units'] = 'm'

        return ds
