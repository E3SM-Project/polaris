import os

import matplotlib.pyplot as plt

from polaris.ocean.model import OceanIOStep, get_days_since_start
from polaris.tasks.ocean.single_column.kpp_regimes.analysis import (
    f11_boundary_layer_depth,
    initial_n_squared,
)
from polaris.viz import mplstyle_context

VARIABLE_ALIASES = {
    'bulkRichardsonNumber': ['bulkRichardsonNumber', 'BulkRichardsonNumber'],
    'vertDiffTopOfCell': ['vertDiffTopOfCell', 'VertDiff'],
    'vertViscTopOfCell': ['vertViscTopOfCell', 'VertVisc'],
    'vertNonLocalFlux': [
        'vertNonLocalFlux',
        'vertNonLocalFluxTemp',
        'VertNonLocalFlux',
    ],
}


class KPPViz(OceanIOStep):
    """
    Plot time series and time-depth KPP diagnostics from single-column runs.
    """

    def __init__(self, component, indir, comparisons, regime):
        super().__init__(component=component, name='kpp_viz', indir=indir)
        self.comparisons = dict(comparisons)
        self.regime = regime
        self.add_output_file('boundary_layer_depth.png')
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/output.nc',
            )
            for variable_name in [
                'bulkRichardsonNumber',
                'vertDiffTopOfCell',
                'vertViscTopOfCell',
                'vertNonLocalFlux',
            ]:
                self.add_output_file(
                    f'{comparison_name}_{variable_name}_time_depth.png'
                )

    def run(self):
        """
        Plot boundary layer depth and KPP profile diagnostics.
        """
        datasets = {}
        for comparison_name in self.comparisons:
            filename = f'{comparison_name}.nc'
            if not os.path.exists(filename):
                continue
            datasets[comparison_name] = self.open_model_dataset(
                filename, decode_times=True, config=self.config
            )

        with mplstyle_context():
            self._plot_boundary_layer_depth(datasets)
            for variable_name in [
                'bulkRichardsonNumber',
                'vertDiffTopOfCell',
                'vertViscTopOfCell',
                'vertNonLocalFlux',
            ]:
                self._plot_time_depth(datasets, variable_name)

    def _plot_boundary_layer_depth(self, datasets):
        """
        Plot mean boundary layer depth over time for each comparison.
        """
        fig, ax = plt.subplots(figsize=(6, 4))
        plotted = False
        for comparison_name, ds in datasets.items():
            if 'boundaryLayerDepth' not in ds:
                continue
            time_days = get_days_since_start(ds)
            bld = ds['boundaryLayerDepth'].mean(dim='nCells')
            ax.plot(time_days, bld, label=comparison_name)
            plotted = True

        if (
            self.regime
            in [
                'kpp_convection_cooling',
                'kpp_convection_evaporation',
                'kpp_cooling_with_mixedlayer',
            ]
            and 'standard' in datasets
        ):
            ds = datasets['standard']
            flux_name = next(
                (
                    name
                    for name in [
                        'surfaceBuoyancyForcing',
                        'SurfaceBuoyancyFlux',
                    ]
                    if name in ds
                ),
                None,
            )
            if flux_name is not None:
                time_days = get_days_since_start(ds)
                f11_bld = f11_boundary_layer_depth(
                    time_days,
                    -float(ds[flux_name].min().values),
                    initial_n_squared(self.config),
                )
                ax.plot(time_days, f11_bld, '--k', label='F11 analytic')

        if not plotted:
            plt.close(fig)
            return
        ax.set_xlabel('Time (days)')
        ax.set_ylabel('Boundary layer depth (m)')
        ax.invert_yaxis()
        ax.legend(frameon=False)
        fig.savefig('boundary_layer_depth.png', bbox_inches='tight')
        plt.close(fig)

    def _plot_time_depth(self, datasets, variable_name):
        """
        Plot each comparison's horizontally averaged diagnostic over time and
        depth.
        """
        for comparison_name, ds in datasets.items():
            source_name = next(
                (
                    name
                    for name in VARIABLE_ALIASES[variable_name]
                    if name in ds
                ),
                None,
            )
            if source_name is None or 'zMid' not in ds:
                continue
            profile = ds[source_name].mean(dim='nCells')
            z_mid = ds['zMid'].mean(dim='nCells')
            vertical_dim = profile.dims[-1]
            if vertical_dim != z_mid.dims[-1]:
                profile = profile.isel({vertical_dim: slice(0, -1)})
            time_days = get_days_since_start(ds)
            if profile.shape[-1] != z_mid.shape[-1]:
                continue

            fig, ax = plt.subplots(figsize=(6, 4))
            mesh = ax.pcolormesh(
                time_days,
                z_mid.transpose().values,
                profile.transpose().values,
                shading='auto',
            )
            ax.set_xlabel('Time (days)')
            ax.set_ylabel('z (m)')
            fig.colorbar(mesh, ax=ax, label=variable_name)
            fig.savefig(
                f'{comparison_name}_{variable_name}_time_depth.png',
                bbox_inches='tight',
            )
            plt.close(fig)
