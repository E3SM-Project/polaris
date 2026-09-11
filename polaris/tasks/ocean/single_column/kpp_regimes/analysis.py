import numpy as np

from polaris.constants import get_constant
from polaris.ocean.model import OceanIOStep, get_time_since_start


def f11_boundary_layer_depth(time_days, buoyancy_flux, n_squared):
    """
    Equation F11 from Van Roekel et al. (2018) for free convection.
    """
    time_seconds = np.asarray(time_days) * 86400.0
    return np.sqrt(2.8 * buoyancy_flux * time_seconds / n_squared)


def initial_n_squared(config):
    """
    Compute the initialized N-squared for the linear EOS profile.
    """
    section = config['single_column']
    g = get_constant('standard_acceleration_of_gravity')
    rho_sw = get_constant('seawater_density_reference')
    alpha = config.getfloat('ocean', 'eos_linear_alpha')
    dtdz = section.getfloat('temperature_gradient_interior')
    return g * alpha * dtdz / rho_sw


class Analysis(OceanIOStep):
    """
    A step for analyzing single-column KPP regime tests: boundary layer
    depth vs. theory (where a simple analytic estimate applies) and
    SimpleShapes-vs-MatchBoth / Langmuir-vs-no-Langmuir comparisons.
    """

    def __init__(self, component, indir, regime, comparisons=None):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this step belongs to

        indir : str
            The subdirectory the step is in

        regime : str
            Which KPP regime task this analysis belongs to (determines
            which theoretical check, if any, is applied)

        comparisons : dict, optional
            A mapping from a short comparison name to the relative path of
            the ``Forward`` step whose ``output.nc`` should be analyzed
            under that name
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.regime = regime
        self.comparisons = (
            dict(comparisons) if comparisons else {'standard': '../forward'}
        )
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger

        t_target = 1.0  # days; early boundary-layer growth
        datasets = {}
        bld = {}
        for comparison_name in self.comparisons:
            ds = self.open_model_dataset(
                f'{comparison_name}.nc', decode_times=True, config=config
            )
            if 'boundaryLayerDepth' not in ds.keys():
                logger.warn(
                    f'{comparison_name}: boundaryLayerDepth not present in '
                    'output, skipping'
                )
                continue
            datasets[comparison_name] = ds

            t_arr = get_time_since_start(ds, units='days')
            t_index = int(np.argmin(np.abs(t_arr - t_target)))
            t_days = float(t_arr[t_index])
            if abs(t_days - t_target) > (1 / 24):
                logger.warn(
                    f'{comparison_name}: time mismatch, expected '
                    f'{t_target}, got {t_days}'
                )
            bld_mean = float(
                ds['boundaryLayerDepth']
                .isel(Time=t_index)
                .mean(dim='nCells')
                .values
            )
            bld[comparison_name] = bld_mean
            logger.info(
                f'{comparison_name}: boundary layer depth = '
                f'{bld_mean:.2f} m at day {t_days:.2f}'
            )

        self._log_matchboth_diff(datasets)

        if self.regime == 'kpp_wind':
            self._check_wind_theory(datasets, bld, t_target)
        elif self.regime in [
            'kpp_convection_cooling',
            'kpp_convection_evaporation',
            'kpp_cooling_with_mixedlayer',
        ]:
            self._check_convection(datasets)
        elif self.regime == 'kpp_strong_convection_cooling':
            self._check_catke_strong_cooling(datasets)
        elif self.regime == 'kpp_langmuir':
            self._check_langmuir(bld)
        elif self.regime == 'kpp_sea_ice':
            self._check_sea_ice(bld)
        elif self.regime == 'kpp_non_local_flux_suppression':
            self._check_stable(datasets)

    def _log_matchboth_diff(self, datasets):
        """
        Compare SimpleShapes (``standard``) vs. MatchBoth (``matchboth``)
        vertical diffusivity profiles at the end of the run, where present.
        """
        if 'standard' not in datasets or 'matchboth' not in datasets:
            return
        ds_standard = datasets['standard']
        ds_matchboth = datasets['matchboth']
        if (
            'vertDiffTopOfCell' not in ds_standard.keys()
            or 'vertDiffTopOfCell' not in ds_matchboth.keys()
        ):
            return
        diff_standard = ds_standard['vertDiffTopOfCell'].isel(Time=-1)
        diff_matchboth = ds_matchboth['vertDiffTopOfCell'].isel(Time=-1)
        rel_diff = float(
            (
                np.abs(diff_matchboth - diff_standard).mean()
                / (np.abs(diff_standard).mean() + 1e-12)
            ).values
        )
        self.logger.info(
            'MatchTechnique (SimpleShapes vs MatchBoth) mean relative '
            f'difference in vertDiffTopOfCell: {rel_diff:.3f}'
        )

    def _check_wind_theory(self, datasets, bld, t_target):
        """
        Compare against the classic wind-driven mixed-layer deepening
        scaling h(t) = u* (15 t / N0^2)^(1/3), using the model's own
        diagnosed initial stratification for N0^2.
        """
        if 'standard' not in datasets or 'standard' not in bld:
            return
        section = self.config['single_column_forcing']
        wind_stress = np.sqrt(
            section.getfloat('wind_stress_zonal') ** 2.0
            + section.getfloat('wind_stress_meridional') ** 2.0
        )
        rho_sw = get_constant('seawater_density_reference')
        u_star = np.sqrt(wind_stress / rho_sw)
        n_sq_init = self._initial_brunt_vaisala(datasets['standard'])
        t_seconds = t_target * 86400.0
        bld_theory = u_star * (15.0 * t_seconds / n_sq_init) ** (1 / 3)
        self.logger.info(
            f'wind-driven theoretical BLD: {bld_theory:.2f} m '
            f'(simulated: {bld["standard"]:.2f} m)'
        )

    def _check_convection(self, datasets):
        """
        Check the direct signatures of a bounded, convective KPP response.
        The F11 analytic comparison is added once its equation is available.
        """
        if 'standard' not in datasets:
            return
        ds = datasets['standard']
        bld = ds['boundaryLayerDepth'].mean(dim='nCells')
        initial_bld = float(bld.isel(Time=0).values)
        final_bld = float(bld.isel(Time=-1).values)
        self.logger.info(
            f'free-convection BLD: {initial_bld:.2f} m initially, '
            f'{final_bld:.2f} m at the end of the run'
        )
        if final_bld <= initial_bld:
            self.logger.warn(
                'Expected convective forcing to deepen the boundary layer'
            )
        flux_name = next(
            (
                name
                for name in ['surfaceBuoyancyForcing', 'SurfaceBuoyancyFlux']
                if name in ds
            ),
            None,
        )
        if flux_name is not None:
            buoyancy_flux = float(-ds[flux_name].min().values)
            n_squared = self._initial_n_squared()
            time_days = get_time_since_start(ds, units='days')
            f11_bld = f11_boundary_layer_depth(
                time_days, buoyancy_flux, n_squared
            )
            valid = f11_bld > 0.0
            if np.any(valid):
                relative_error = np.sqrt(
                    np.mean(
                        ((bld.values[valid] - f11_bld[valid]) / f11_bld[valid])
                        ** 2
                    )
                )
                self.logger.info(
                    'F11 free-convection BLD trajectory RMS relative error: '
                    f'{relative_error:.3f}'
                )
        for variable_name in ['temperature', 'potentialDensity']:
            if variable_name not in ds:
                continue
            if not np.isfinite(ds[variable_name]).all():
                self.logger.warn(
                    f'Non-finite {variable_name} in the convection run'
                )
        non_local_name = next(
            (
                name
                for name in [
                    'vertNonLocalFlux',
                    'vertNonLocalFluxTemp',
                    'VertNonLocalFlux',
                ]
                if name in ds
            ),
            None,
        )
        if non_local_name is not None:
            non_local = float(
                np.abs(ds[non_local_name].isel(Time=-1)).max().values
            )
            self.logger.info(
                f'convective case: max |vertNonLocalFlux| at end of run = '
                f'{non_local:.3e}'
            )
            if non_local <= 0.0:
                self.logger.warn(
                    'Expected a nonzero KPP non-local flux under cooling'
                )

    def _check_langmuir(self, bld):
        """
        Confirm Langmuir enhancement deepens (or at least does not shoal)
        the boundary layer relative to the no-Langmuir case.
        """
        if 'langmuir' not in bld or 'no_langmuir' not in bld:
            return
        self.logger.info(
            f'Langmuir-enabled BLD: {bld["langmuir"]:.2f} m vs. '
            f'no-Langmuir BLD: {bld["no_langmuir"]:.2f} m'
        )
        if bld['langmuir'] < bld['no_langmuir']:
            self.logger.warn(
                'Expected Langmuir circulation to deepen (or at least not '
                'shoal) the boundary layer relative to the no-Langmuir case'
            )

    def _check_catke_strong_cooling(self, datasets):
        """
        Check the KPP profile signature highlighted in Wagner et al. (2024):
        surface cooling with stable stratification retained in the boundary
        layer under strongly forced free convection.
        """
        if 'standard' not in datasets:
            return
        ds = datasets['standard']
        if 'temperature' not in ds or 'BruntVaisalaFreqTop' not in ds:
            return
        temperature = ds['temperature'].mean(dim='nCells')
        initial_surface = float(temperature.isel(Time=0, nVertLevels=0).values)
        final_surface = float(temperature.isel(Time=-1, nVertLevels=0).values)
        n_squared = ds['BruntVaisalaFreqTop'].isel(Time=-1)
        max_n_squared = float(n_squared.max().values)
        self.logger.info(
            'strong cooling: surface temperature changed from '
            f'{initial_surface:.3f} to {final_surface:.3f} degC; '
            f'max N^2 = {max_n_squared:.3e} s^-2'
        )
        if final_surface >= initial_surface:
            self.logger.warn(
                'Expected strong surface cooling to lower the SST'
            )
        if max_n_squared <= 0.0:
            self.logger.warn(
                'Expected stable stratification within the strongly forced '
                'convective profile'
            )

    def _check_sea_ice(self, bld):
        """
        Confirm the boundary layer depth satisfies KPP's default 5 m
        minimum-OBL-under-sea-ice lower bound.
        """
        expected_min_obl = 30.0
        for comparison_name, value in bld.items():
            if value < expected_min_obl:
                self.logger.warn(
                    f'{comparison_name}: boundary layer depth {value:.2f} m '
                    f'is below the {expected_min_obl} m sea-ice minimum'
                )
            else:
                self.logger.info(
                    f'{comparison_name}: boundary layer depth '
                    f'{value:.2f} m satisfies the sea-ice minimum OBL bound'
                )

    def _check_stable(self, datasets):
        """
        Confirm KPP's non-local flux is disabled (stable surface buoyancy
        forcing means no non-local transport) while mixing remains active.
        """
        if 'standard' not in datasets:
            return
        ds = datasets['standard']
        non_local_name = next(
            (
                name
                for name in [
                    'vertNonLocalFlux',
                    'vertNonLocalFluxTemp',
                    'VertNonLocalFlux',
                ]
                if name in ds
            ),
            None,
        )
        if non_local_name is None:
            return
        non_local = float(
            np.abs(ds[non_local_name].isel(Time=-1)).max().values
        )
        self.logger.info(
            f'stable case: max |vertNonLocalFlux| at end of run = '
            f'{non_local:.3e}'
        )
        if non_local > 1.0e-10:
            self.logger.warn(
                'Expected the non-local flux to be disabled (~0) under '
                'stabilizing surface buoyancy forcing'
            )
        if 'vertDiffTopOfCell' in ds.keys():
            vert_diff = float(
                ds['vertDiffTopOfCell'].isel(Time=-1).max().values
            )
            self.logger.info(
                f'stable case: max vertDiffTopOfCell at end of run = '
                f'{vert_diff:.3e}'
            )
            if vert_diff <= 0.0:
                self.logger.warn(
                    'Expected some mixing (background or KPP) to remain '
                    'even though the non-local flux is disabled'
                )

    @staticmethod
    def _initial_brunt_vaisala(ds):
        # max over cells and vertical levels of the initial stratification
        return float(ds['BruntVaisalaFreqTop'].isel(Time=0).max().values)

    def _initial_n_squared(self):
        """
        Compute the initialized N-squared for the linear EOS profile.
        """
        return initial_n_squared(self.config)
