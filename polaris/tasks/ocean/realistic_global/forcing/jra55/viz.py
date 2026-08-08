import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_lat_lon_field, use_mplstyle

from .stress import JRA55_STRESS_FILENAME


class Jra55VizStep(Step):
    """
    A step for visualizing the derived JRA55-do wind-stress product.

    The zonal-mean ``taux`` curve is the most diagnostic view: it is what
    should be compared against published JRA/CORE stress climatologies to
    confirm the bulk formula and air density are right.

    Attributes
    ----------
    stress_step : polaris.Step
        The upstream step that produces the wind-stress product.
    """

    def __init__(self, component, subdir, stress_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stress_step : polaris.Step
            The step that produces the JRA55-do wind-stress product.
        """
        super().__init__(
            component=component,
            name='viz',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.stress_step = stress_step

    def setup(self):
        """
        Set up input and output files for the step.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_STRESS_FILENAME,
            work_dir_target=(
                f'{self.stress_step.path}/{JRA55_STRESS_FILENAME}'
            ),
        )
        for filename in [
            'taux.png',
            'tauy.png',
            'tau_mag.png',
            'zonal_mean_taux.png',
        ]:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Plot global maps of the stress components and magnitude, plus the
        zonal-mean zonal stress.
        """
        use_mplstyle()
        config = self.config
        with xr.open_dataset(JRA55_STRESS_FILENAME) as ds:
            lon = ds.lon.values
            lat = ds.lat.values
            taux = ds.taux.values
            tauy = ds.tauy.values

        tau_mag = np.sqrt(taux**2 + tauy**2)
        fields = {
            'taux': (taux, 'zonal wind stress (N m$^{-2}$)'),
            'tauy': (tauy, 'meridional wind stress (N m$^{-2}$)'),
            'tau_mag': (tau_mag, 'wind stress magnitude (N m$^{-2}$)'),
        }
        for name, (field, label) in fields.items():
            plot_global_lat_lon_field(
                lon=lon,
                lat=lat,
                data_array=field,
                out_filename=f'{name}.png',
                config=config,
                colormap_section=f'jra55_viz_{name}',
                title=label,
                colorbar_label='N m$^{-2}$',
            )

        self._plot_zonal_mean(lat=lat, taux=taux)

    @staticmethod
    def _plot_zonal_mean(lat, taux):
        """
        Plot the zonal-mean zonal stress against latitude.
        """
        plt.figure(figsize=(5, 6))
        plt.plot(taux.mean(axis=1), lat, color='k')
        plt.axvline(0.0, color='0.7', linewidth=0.8)
        plt.xlabel(r'zonal-mean $\tau_x$ (N m$^{-2}$)')
        plt.ylabel('latitude')
        plt.title('Zonal-mean zonal wind stress')
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig('zonal_mean_taux.png')
        plt.close()
