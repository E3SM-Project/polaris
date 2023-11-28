import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.ocean.viz import compute_transect, plot_transect
from polaris.viz import plot_horiz_field


class Viz(Step):
    """
    A step for visualizing a cross-section and horizontal planes through the
    ice shelf
    """
    def __init__(self, component, indir, mesh, init):
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
            target=f'{mesh.path}/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target=f'{init.path}/init.nc')
        self.add_input_file(
            filename='adjusted_init.nc',
            target='../forward/init.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the test case
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        ds_init = xr.load_dataset('init.nc')
        ds = xr.load_dataset('output.nc')

        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))

        # TODO add derived variable delSsh, delLandIcePressure to ds
        # for tidx=0, ds.isel(Time=tidx) - ds_init.isel(Time=0)
        # for tidx>0, ds.isel(Time=tidx) - ds.isel(Time=0)
        # TODO add derived variable columnThickness to ds_init and ds
        # Plot the time series of max velocity
        plt.figure(figsize=[12, 6], dpi=100)
        umax = np.amax(ds.velocityX[:, :, 0].values, axis=1)
        vmax = np.amax(ds.velocityY[:, :, 0].values, axis=1)
        t = ds.daysSinceStartOfSim.values
        time = pd.to_timedelta(t) / 1.e9
        plt.plot(time, umax, 'k', label='u')
        plt.plot(time, vmax, 'b', label='v')
        plt.xlabel('Time (s)')
        plt.ylabel('Velocity (m/s)')
        plt.legend()
        plt.savefig('velocity_max_t.png', dpi=200)
        plt.close()

        vmin_del_ssh = np.min(ds.delSsh.values)
        vmax_del_ssh = np.max(ds.delSsh.values)
        vmin_del_p = np.min(ds.delLandIcePressure.values)
        vmax_del_p = np.max(ds.delLandIcePressure.values)
        vmin_temp = np.min(ds.temperature.values)
        vmax_temp = np.max(ds.temperature.values)
        vmin_salt = np.min(ds.salinity.values)
        vmax_salt = np.max(ds.salinity.values)
        vmax_uv = max(np.amax(ds.velocityX.values),
                      np.amax(ds.velocityY.values))

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

        plot_transect(ds_transect,
                      mpas_field=ds_init.salinity.isel(Time=tidx),
                      out_filename='salinity_section_init.png',
                      title='salinity',
                      interface_color='grey',
                      vmin=vmin_salt, vmax=vmax_salt,
                      colorbar_label=r'PSU', cmap='cmo.haline')

        # Plot water column thickness horizontal ds_init
        cell_mask = ds_init.maxLevelCell >= 1
        ds_horiz = self._process_ds(ds_init, ds_init, ds_mesh.bottomDepth,
                                    time_index=0)
        plot_horiz_field(ds_init, ds_mesh, 'columnThickness',
                         'H_horiz_init.png', t_index=0,
                         cell_mask=cell_mask)
        # Plot land ice pressure horizontal ds_init
        for tidx in [0, -1]:
            ds_horiz = self._process_ds(ds, ds_init, ds_mesh.bottomDepth,
                                        time_index=tidx)
            day = ds.daysSinceStartOfSim.isel(Time=tidx)
            # Plot water column thickness horizontal
            plot_horiz_field(ds_horiz, ds_mesh, 'columnThickness',
                             f'H_horiz_day{int(day)}.png', t_index=tidx,
                             cell_mask=cell_mask)
            plot_horiz_field(ds_horiz, ds_mesh, 'wettingVelocityFactor',
                             f'wet_horiz_day{int(day)}.png', t_index=tidx,
                             z_index=0, cell_mask=cell_mask, vmin=0, vmax=1,
                             cmap='cmo.ice')
            # Plot difference in ssh
            plot_horiz_field(ds_horiz, ds_mesh, 'delSsh',
                             f'del_ssh_horiz_day{int(day)}.png', t_index=tidx,
                             cell_mask=cell_mask,
                             vmin=vmin_del_ssh, vmax=vmax_del_ssh)

            # Plot difference in land ice pressure
            plot_horiz_field(ds_horiz, ds_mesh, 'delLandIcePressure',
                             f'del_land_ice_pressure_horiz_day{int(day)}.png',
                             t_index=tidx, cell_mask=cell_mask,
                             vmin=vmin_del_p, vmax=vmax_del_p)

            # Plot transects
            ds_transect = compute_transect(
                x=x, y=y, ds_horiz_mesh=ds_mesh,
                layer_thickness=ds.layerThickness.isel(Time=tidx),
                bottom_depth=ds_mesh.bottomDepth,
                min_level_cell=ds_mesh.minLevelCell - 1,
                max_level_cell=ds_mesh.maxLevelCell - 1,
                spherical=False)

            plot_transect(ds_transect,
                          mpas_field=ds.velocityX.isel(Time=tidx),
                          out_filename=f'u_section_day{int(day)}.png',
                          title='x-velocity',
                          interface_color='grey',
                          vmin=-vmax_uv, vmax=vmax_uv,
                          colorbar_label=r'm/s', cmap='cmo.balance')

            plot_transect(ds_transect,
                          mpas_field=ds.velocityY.isel(Time=tidx),
                          out_filename=f'v_section_day{int(day)}.png',
                          title='x-velocity',
                          interface_color='grey',
                          vmin=-vmax_uv, vmax=vmax_uv,
                          colorbar_label=r'm/s', cmap='cmo.balance')

            plot_transect(
                ds_transect,
                mpas_field=ds.temperature.isel(Time=tidx),
                out_filename=f'temperature_section_day{int(day)}.png',
                title='temperature',
                interface_color='grey',
                vmin=vmin_temp, vmax=vmax_temp,
                colorbar_label=r'$^{\circ}$C', cmap='cmo.thermal')

            plot_transect(ds_transect,
                          mpas_field=ds.salinity.isel(Time=tidx),
                          out_filename=f'salinity_section_day{int(day)}.png',
                          title='salinity',
                          interface_color='grey',
                          vmin=vmin_salt, vmax=vmax_salt,
                          colorbar_label=r'PSU', cmap='cmo.haline')

    @staticmethod
    def _process_ds(ds, ds_init, bottom_depth, time_index):
        ds_out = ds.isel(Time=time_index, nVertLevels=0)
        ds_out['columnThickness'] = ds_out.ssh + bottom_depth
        if time_index == 0:
            ds_out['delSsh'] = ds_out.ssh - ds_init.ssh.isel(Time=0)
            ds_out['delLandIcePressure'] = ds_out.landIcePressure - \
                ds_init.landIcePressure.isel(Time=0)
        else:
            ds_out['delSsh'] = ds_out.ssh - ds.ssh.isel(Time=0)
            ds_out['delLandIcePressure'] = ds_out.landIcePressure - \
                ds.landIcePressure.isel(Time=0)
        return ds_out
