import numpy as np

from polaris.constants import get_constant
from polaris.ocean.model import (
    OceanIOStep,
    get_days_since_start,
)
from polaris.ocean.vertical import (
    compute_zint_zmid_from_layer_thickness,
)


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
        self.add_input_file(
            filename='vert_coord.nc', target='../init/vert_coord.nc'
        )
        self.comparisons = (
            dict(comparisons)
            if comparisons
            else {'forward': '../forward/output.nc'}
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
        ds_vert = self.open_model_dataset(
            'vert_coord.nc',
            decode_times=False,
            config=self.config,
        )
        for comparison_name in self.comparisons.keys():
            ds_diags = self.open_model_dataset(
                f'{comparison_name}.nc', decode_times=True, config=self.config
            )
            if 'BruntVaisalaFreqTop' not in ds_diags.keys():
                self.logger.warn(
                    f'BruntVailsalaFreqTop not present in ds {comparison_name}'
                    ' skipping BLD comparison'
                )
                continue
            t_target = 1.0  # empirical relationship hold for up to 30h
            t_arr = get_days_since_start(ds_diags)
            t_index = np.argmin(np.abs(t_arr - t_target))
            t_days = float(t_arr[t_index])
            if abs(t_days - t_target) > (1 / 24):
                self.logger.warn(
                    f'{comparison_name}: Time mismatch \n'
                    f'expected {t_target}, got {t_days}'
                )
            ds_diags_1day = ds_diags.isel(Time=t_index)
            N_sq = ds_diags_1day['BruntVaisalaFreqTop'].mean(dim='nCells')
            if 'zTop' in ds_diags_1day.keys():
                z_top_final = ds_diags_1day['zTop'].mean(dim='nCells')
            else:
                z_int_final, _ = compute_zint_zmid_from_layer_thickness(
                    layer_thickness=ds_diags_1day['layerThickness'],
                    bottom_depth=ds_vert['bottomDepth'],
                    min_level_cell=ds_vert['minLevelCell'] - 1,
                    max_level_cell=ds_vert['maxLevelCell'] - 1,
                )
                z_top_final = z_int_final[:-1].mean(dim='nCells')
                z_top_final = z_top_final.rename(
                    {'nVertLevelsP1': 'nVertLevels'}
                )
            index_bld = int(np.nanargmax(N_sq.values))
            bld = z_top_final.isel(nVertLevels=index_bld)
            self.logger.info(
                f'{comparison_name}: Boundary layer depth computed from '
                f'max(N^2) depth {bld.values} m'
            )
            if comparison_name == 'no_hadv':
                section = self.config['single_column_forcing']
                wind_stress = np.sqrt(
                    section.getfloat('wind_stress_zonal') ** 2.0
                    + section.getfloat('wind_stress_meridional') ** 2.0
                )
                RhoSw = get_constant('seawater_density_reference')
                u_star = wind_stress / RhoSw
                # N_sq_init only corresponds to the default config parameters
                # TODO compute this based on config parameters
                N_sq_init = 1.0e-4
                bld_theory = -u_star * (
                    15.0 * t_days * 86400.0 / N_sq_init
                ) ** (1 / 3)
                self.logger.info(
                    f'{comparison_name}: Theoretical BL depth: {bld_theory} m'
                )
