import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.time import get_days_since_start

# TODO import rho_0 from constants


class Analysis(OceanIOStep):
    """
    A step for analyzing the results of a single-column wind-forced test
    """

    def __init__(
        self,
        component,
        indir,
        comparisons=None,
    ):
        super().__init__(component=component, name='analysis', indir=indir)
        self.comparisons = (
            dict(comparisons)
            if comparisons
            else {'forward': '../forward/output.nc'}
        )
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}_diags.nc',
                target=f'{comparison_path}/output/KPP_test.0001-01-01_00.00.00.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        section = self.config['single_column_forcing']
        wind_stress = np.sqrt(
            section.getfloat('wind_stress_zonal') ** 2.0
            + section.getfloat('wind_stress_meridional') ** 2.0
        )
        # u_star = 0.01
        rho_0 = 1026.0
        u_star = wind_stress / rho_0
        # TODO why is this 0
        # u_star = ds_diags_1day['surfaceFrictionVelocity'].mean(dim='nCells')
        # TODO compute this based on config parameters
        N_sq_init = 1.0e-4
        for comparison_name in self.comparisons.keys():
            ds_diags = self.open_model_dataset(
                f'{comparison_name}_diags.nc', decode_times=False
            )
            t_target = 1.0  # empirical relationship hold for up to 30h
            t_arr = get_days_since_start(ds_diags)
            t_index = np.argmin(np.abs(t_arr - t_target))
            t_days = float(t_arr[t_index])
            if abs(t_days - t_target) > (1 / 24):
                self.logger.warn(
                    f'{comparison_name}: Time mismatch \n'
                    f'expected {t_target}, got {t_days}'
                )
            bld_theory = u_star * (15.0 * t_days * 86400.0 / N_sq_init) ** (
                1 / 3
            )
            ds_diags_1day = ds_diags.isel(Time=t_index)
            z_top_final = ds_diags_1day['zTop'].mean(dim='nCells')
            N_sq = ds_diags_1day['BruntVaisalaFreqTop'].mean(dim='nCells')
            index_bld = int(np.nanargmax(N_sq.values))
            bld = z_top_final.isel(nVertLevels=index_bld)
            self.logger.info(
                f'{comparison_name}: boundary layer depth '
                f'expected {bld_theory}, actual {bld.values}'
            )
