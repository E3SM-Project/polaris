import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.viz.transect import compute_transect, plot_transect


class Viz(Step):
    """
    A step for visualizing a cross-section through the internal wave
    """
    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        test_case : compass.TestCase
            The test case this step belongs to
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.add_input_file(
            filename='mesh.nc',
            target='../../../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../../../init/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the test case
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        y = np.linspace(y_min.values, y_max.values, 11)
        x = x_mid.values * np.ones_like(y)
        x = xr.DataArray(data=x, dims=('nPoints',))
        y = xr.DataArray(data=y, dims=('nPoints',))
        ds_transect = compute_transect(x, y, ds_mesh, spherical=False)

        ds = xr.load_dataset('output.nc')
        for tidx in range(ds.sizes['Time']):
            plot_transect(ds_transect, ds.temperature.isel(Time=tidx),
                          'temperature_depth_{tidx:g}.png', 'temperature',
                          colorbar_label=r'$^{\circ}$C', cmap='cmo.thermal')
            plot_transect(ds_transect, ds.layerThickness.isel(Time=tidx),
                          'layer_thickness_depth_{tidx:g}.png',
                          'layer thickness',
                          colorbar_label=r'm', cmap='cmo.thermal')
            plot_transect(ds_transect, ds.vertVelocityTop.isel(Time=tidx),
                          'vertical_velocity_depth_{tidx:g}.png',
                          'vertical velocity',
                          colorbar_label='m/s', cmap='cmo.balance')
