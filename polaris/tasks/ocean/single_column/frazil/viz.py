import numpy as np

from polaris.ocean.model import get_time_since_start
from polaris.tasks.ocean.single_column.frazil.utils import (
    FRAZIL_RATE_UNITS,
    _plot_frazil_fluxes,
)
from polaris.tasks.ocean.single_column.viz import Viz
from polaris.viz import mplstyle_context


class FrazilViz(Viz):
    """Plot standard column profiles and Omega frazil flux histories."""

    def __init__(self, component, indir, init, **kwargs):
        super().__init__(component=component, indir=indir, init=init, **kwargs)
        self.has_latent_heat_flux = 'latent_heat_flux' in init.forcing_vars

    def run(self):
        super().run()
        if self.config.get('ocean', 'model') != 'omega':
            return

        series = []
        for name in self.comparisons:
            with self.open_model_dataset(
                f'{name}.nc', config=self.config, decode_times=True
            ) as ds:
                missing = [
                    field for field in FRAZIL_RATE_UNITS if field not in ds
                ]
                if missing:
                    raise ValueError(
                        f'Missing frazil flux fields for {name}: '
                        + ', '.join(missing)
                    )
                series.append(
                    {
                        'name': name,
                        'history_hours': np.asarray(
                            get_time_since_start(ds, units='hours')
                        ),
                        'frazil_rates': {
                            field: np.asarray(ds[field].mean('nCells').values)
                            for field in FRAZIL_RATE_UNITS
                        },
                    }
                )

        styles = {
            name: {
                'linestyle': '--' if name == 'FixedProperty' else '-',
            }
            for name in self.comparisons
        }
        count = max(len(item['history_hours']) for item in series)
        heat_flux = 0.0
        if self.has_latent_heat_flux:
            heat_flux = self.config.getfloat(
                'single_column_forcing', 'latent_heat_flux'
            )
        with mplstyle_context():
            _plot_frazil_fluxes(series, styles, heat_flux, count)
