import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.viz import compute_transect, plot_transect


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
        ds_mesh = xr.load_dataset('init.nc')
        ds_init = ds_mesh
        ds = xr.load_dataset('output.nc')

        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))

        vmin_temp = np.min(ds.temperature.values)
        vmax_temp = np.max(ds.temperature.values)
        vmax_v = np.max(np.abs(ds.vertVelocityTop.values))

        tidx = 0  # Plot the initial time
        ds_transect = compute_transect(
            x=x, y=y, ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_init.layerThickness.isel(Time=tidx),
            bottom_depth=ds_mesh.bottomDepth,
            min_level_cell=ds_mesh.minLevelCell - 1,
            max_level_cell=ds_mesh.maxLevelCell - 1,
            spherical=False)

        plot_transect(ds_transect,
                      mpas_field=ds_init.temperature.isel(Time=tidx),
                      out_filename='temperature_section_init.png',
                      title='temperature',
                      interface_color='grey',
                      vmin=vmin_temp, vmax=vmax_temp,
                      colorbar_label=r'$^{\circ}$C', cmap='cmo.thermal')

        tidx = -1  # Plot the final time
        ds_transect = compute_transect(
            x=x, y=y, ds_horiz_mesh=ds_mesh,
            layer_thickness=ds.layerThickness.isel(Time=tidx),
            bottom_depth=ds_mesh.bottomDepth,
            min_level_cell=ds_mesh.minLevelCell - 1,
            max_level_cell=ds_mesh.maxLevelCell - 1,
            spherical=False)

        plot_transect(ds_transect,
                      mpas_field=ds.temperature.isel(Time=tidx),
                      out_filename='temperature_section_final.png',
                      title='temperature',
                      interface_color='grey',
                      vmin=vmin_temp, vmax=vmax_temp,
                      colorbar_label=r'$^{\circ}$C', cmap='cmo.thermal')
        w_values = ds.vertVelocityTop.isel(Time=tidx).values[:, :-1]
        w = w_values * xr.ones_like(ds.temperature.isel(Time=tidx))
        plot_transect(
            ds_transect,
            mpas_field=w,
            out_filename='vertical_velocity_section_final.png',
            title='vertical velocity',
            vmin=-vmax_v, vmax=vmax_v,
            colorbar_label='m/s', cmap='cmo.balance')
