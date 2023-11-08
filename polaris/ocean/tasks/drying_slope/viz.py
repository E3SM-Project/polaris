import os

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
    A step for plotting the results of a series of drying_slope runs
    """
    def __init__(self, component, indir=None, subdir=None, name='viz',
                 damping_coeffs=[],
                 coord_type='sigma', baroclinic=False,
                 forcing_type='tidal_cycle'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name=name, indir=indir,
                         subdir=subdir)

        self.damping_coeffs = damping_coeffs
        self.coord_type = coord_type
        self.forcing_type = forcing_type
        self.baroclinic = baroclinic

        self.add_input_file(
            filename='mesh.nc',
            target='../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../init/initial_state.nc')
        self.add_input_file(
            filename='forcing.nc',
            target='../init/forcing.nc')
        # TODO change this for damping_coeff outputs
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the task
        """
        self._plot_ssh_time_series(forcing_type=self.forcing_type)
        ds_mesh = xr.load_dataset('init.nc')
        cell_mask = ds_mesh.maxLevelCell >= 1
        # TODO change this for damping_coeff outputs
        ds = xr.load_dataset('output.nc')

        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))

        ymin = -ds_mesh.bottomDepth.max()
        ymax = ds.ssh.max()
        vmin_layer_thickness = ds.layerThickness.min()
        vmax_layer_thickness = ds.layerThickness.max()
        vmax_velocity = np.max(np.abs(ds.velocityY.values))
        nrows = 2
        if self.baroclinic:
            nrows += 1
            section = self.config['drying_slope_baroclinic']
            vmin_salinity = section.getfloat('left_salinity')
            vmax_salinity = section.getfloat('right_salinity')
        mpastime = ds.daysSinceStartOfSim.values
        simtime = pd.to_timedelta(mpastime)
        time_hours = simtime.total_seconds() / 3600.
        for tidx in range(ds.sizes['Time']):
            ds_transect = compute_transect(
                x=x, y=y, ds_horiz_mesh=ds_mesh,
                layer_thickness=ds.layerThickness.isel(Time=tidx),
                bottom_depth=ds.bottomDepth,
                min_level_cell=ds.minLevelCell - 1,
                max_level_cell=ds.maxLevelCell - 1,
                spherical=False)

            plot_horiz_field(ds, ds_mesh,
                             'wettingVelocityFactor',
                             f'wetting_velocity_factor_horiz_t{tidx:03g}.png',
                             transect_x=x, transect_y=y,
                             show_patch_edges=True, t_index=tidx,
                             cell_mask=cell_mask, vmin=0, vmax=1)

            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.velocityX.isel(Time=tidx),
                title='Across-slope velocity',
                out_filename=f'velocityX_depth_t{tidx:03g}.png',
                vmin=-vmax_velocity, vmax=vmax_velocity,
                colorbar_label=r'', cmap='cmo.balance')

            fig, axs = plt.subplots(nrows, sharex=True, figsize=(5, 3 * nrows))
            fig.suptitle(f'Time: {time_hours[tidx]:2.1f} hours')
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.layerThickness.isel(Time=tidx),
                ax=axs[0],
                outline_color=None, ssh_color='blue', seafloor_color='black',
                interface_color='grey',
                vmin=vmin_layer_thickness, vmax=vmax_layer_thickness,
                colorbar_label=r'm', cmap='cmo.thermal')
            axs[0].set_title('Layer thickness')
            axs[0].set_ylim([ymin, ymax])
            axs[0].set_xlabel(None)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.velocityY.isel(Time=tidx),
                ax=axs[1],
                outline_color=None, ssh_color='blue', seafloor_color='black',
                vmin=-vmax_velocity, vmax=vmax_velocity,
                colorbar_label='m/s', cmap='cmo.balance')
            axs[1].set_title('Along-slope velocity')
            axs[1].set_ylim([ymin, ymax])
            axs[1].set_xlabel(None)
            if self.baroclinic:
                plot_transect(
                    ds_transect=ds_transect,
                    mpas_field=ds.salinity.isel(Time=tidx),
                    ax=axs[2],
                    outline_color=None, ssh_color='blue',
                    seafloor_color='black',
                    vmin=vmin_salinity, vmax=vmax_salinity,
                    colorbar_label=r'PSU', cmap='cmo.haline')
                axs[2].set_title('Salinity')
                axs[2].set_ylim([ymin, ymax])
            plt.savefig(f'layerThickness_velocityY_depth_t{tidx:03g}.png',
                        bbox_inches='tight')
            plt.close()

            if self.baroclinic:
                # We can't plot wettingVelocityBaroclinic transect because it
                # is on edges
                plot_horiz_field(
                    ds, ds_mesh,
                    'wettingVelocityBarotropicSubcycle',
                    f'wettingVelocityBarotropicSubcycle_horiz_t{tidx:03g}.png',
                    t_index=tidx,
                    cell_mask=cell_mask, vmin=0, vmax=1)
                self._plot_salinity(tidx=-1, y_distance=45.)
        if not self.damping_coeffs:
            for tidx in range(ds.sizes['Time']):
                plot_horiz_field(ds, ds_mesh,
                                 'ssh',
                                 f'ssh_horiz_t{tidx:03g}.png',
                                 t_index=tidx,
                                 cell_mask=cell_mask)
        else:
            self._plot_ssh_validation()

    def _forcing(self, t):
        ssh = 10. * np.sin(t * np.pi / 12.) - 10.
        return ssh

    def _plot_salinity(self, tidx=None, y_distance=0., outFolder='.'):
        """
        Plot salinity at a point location as a function of vertical levels
        y_distance distance in meters along y-axis
        """
        ds = xr.open_dataset('output.nc')
        y_cell = ds.yCell
        cell_idx = np.argmin(y_cell.values - y_distance / 1e3)
        salinity = ds['salinity'][tidx, cell_idx, :]
        fig = plt.figure()
        vert_levels = ds.dims['nVertLevels']
        plt.plot(salinity, np.arange(vert_levels), '.-')
        plt.xlabel('Salinity')
        plt.ylabel('Vertical level')
        fig.savefig('salinity_levels.png', bbox_inches='tight', dpi=200)
        plt.close(fig)

    def _plot_ssh_time_series(self, outFolder='.', forcing_type='tidal_cycle'):
        """
        Plot ssh forcing on the right x boundary as a function of time against
        the analytical solution. The agreement should be within machine
        precision if the namelist options are consistent with the Warner et al.
        (2013) test case.
        """
        figsize = [6.4, 4.8]

        damping_coeffs = self.damping_coeffs
        if not damping_coeffs:
            naxes = 1
            ncFilename = ['output.nc']
        else:
            naxes = len(damping_coeffs)
            ncFilename = [f'output_{damping_coeff}.nc'
                          for damping_coeff in damping_coeffs]
        fig, _ = plt.subplots(nrows=naxes, ncols=1, figsize=figsize, dpi=100)

        ds_forcing = xr.open_dataset('../init/forcing.nc')
        mask = ds_forcing.tidalInputMask
        for i in range(naxes):
            ax = plt.subplot(naxes, 1, i + 1)
            ds = xr.open_dataset(ncFilename[i])
            ympas = ds.ssh.where(mask).mean('nCells').values
            xmpas = np.linspace(0, 1.0, len(ds.xtime)) * 12.0
            ax.plot(xmpas, ympas, marker='o', label='MPAS-O forward',
                    color='k')
            if forcing_type == 'tidal_cycle':
                xSsh = np.linspace(0, 12.0, 100)
                ySsh = self._forcing(t=xSsh)
                ax.plot(xSsh, ySsh, lw=3, label='analytical', color='b')
            ax.set_ylabel('Tidal amplitude (m)')
            ax.set_xlabel('Time (hrs)')
            ax.legend(frameon=False)
            ax.label_outer()
            ds.close()

        fig.suptitle('Tidal amplitude forcing (right side)')
        fig.savefig(f'{outFolder}/ssh_t.png', bbox_inches='tight', dpi=200)

        plt.close(fig)

    def _plot_ssh_validation(self, tidx=None, outFolder='.'):
        """
        Plot ssh as a function of along-channel distance for all times for
        which there is validation data
        """
        datatypes = ['analytical', 'ROMS']
        times = ['0.05', '0.15', '0.25', '0.30', '0.40', '0.50']
        colors = {'MPAS-O': 'k', 'analytical': 'b', 'ROMS': 'g'}

        locs = [7.2, 2.2, 0.2, 1.2, 4.2, 9.3]
        locs = 0.92 - np.divide(locs, 11.)

        damping_coeffs = self.damping_coeffs

        if damping_coeffs is None:
            naxes = 1
            nhandles = 1
            ncFilename = ['output.nc']
        else:
            naxes = len(damping_coeffs)
            nhandles = len(datatypes) + 1
            ncFilename = [f'output_{damping_coeff}.nc'
                          for damping_coeff in damping_coeffs]

        ds_mesh = xr.open_dataset('init.nc')
        mesh_ymean = ds_mesh.isel(Time=0).groupby('yCell').mean(
            dim=xr.ALL_DIMS)
        bottom_depth = mesh_ymean.bottomDepth.values
        drying_length = self.config.getfloat('drying_slope', 'ly_analysis')
        right_bottom_depth = self.config.getfloat('drying_slope',
                                                  'right_bottom_depth')
        drying_length = drying_length
        x_offset = np.max(mesh_ymean.yCell.values) - drying_length * 1000.
        x = (mesh_ymean.yCell.values - x_offset) / 1000.0

        xBed = np.linspace(0, drying_length, 100)
        yBed = right_bottom_depth / drying_length * xBed

        fig, _ = plt.subplots(nrows=naxes, ncols=1, sharex=True)

        for i in range(naxes):
            ax = plt.subplot(naxes, 1, i + 1)
            ds = xr.open_dataset(ncFilename[i])
            ds = ds.drop_vars(np.setdiff1d(
                [j for j in ds.variables],
                ['daysSinceStartOfSim', 'yCell', 'ssh']))

            ax.plot(xBed, yBed, '-k', lw=3)
            ax.set_xlim(0, drying_length)
            ax.set_ylim(-1, 1.1 * right_bottom_depth)
            ax.invert_yaxis()
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.label_outer()

            for atime, ay in zip(times, locs):

                # Plot MPAS-O data
                # factor of 1e- needed to account for annoying round-off issue
                # to get right time slices
                mpastime = ds.daysSinceStartOfSim.values
                simtime = pd.to_timedelta(mpastime)
                s_day = 86400.
                time = simtime.total_seconds()
                plottime = np.argmin(np.abs(time / s_day - float(atime)))
                ymean = ds.isel(Time=plottime).groupby('yCell').mean(
                    dim=xr.ALL_DIMS)
                y = ymean.ssh.values

                ax.plot(x, -y, label='MPAS-O', color=colors['MPAS-O'])
                if damping_coeffs is not None:
                    ax.text(0.5, 5, 'r = ' + str(damping_coeffs[i]))
                    # Plot comparison data
                    if tidx is not None:
                        plt.title(f'{atime:03f} days')
                        for atime, ay in zip(times, locs):
                            ax.text(1, ay, f'{atime} days', size=8,
                                    transform=ax.transAxes)
                            for datatype in datatypes:
                                datafile = f'./r{damping_coeffs[i]}d{atime}-'\
                                           f'{datatype.lower()}.csv'
                                if os.path.exists(datafile):
                                    data = pd.read_csv(datafile, header=None)
                                    ax.scatter(data[0], data[1], marker='.',
                                               color=colors[datatype],
                                               label=datatype)
                    else:
                        ax.text(1, ay, f'{atime} days', size=8,
                                transform=ax.transAxes)
                        for datatype in datatypes:
                            datafile = f'./r{damping_coeffs[i]}d{atime}-'\
                                       f'{datatype.lower()}.csv'
                            if os.path.exists(datafile):
                                data = pd.read_csv(datafile, header=None)
                                ax.scatter(data[0], data[1], marker='.',
                                           color=colors[datatype],
                                           label=datatype)
            # Plot bottom depth, but line will not be visible unless bottom
            # depth is incorrect
            ax.plot(x, bottom_depth, ':k')
            ax.legend(frameon=False, loc='lower left')

            ds.close()

            h, l0 = ax.get_legend_handles_labels()
            ax.legend(h[:nhandles], l0[:nhandles], frameon=False,
                      loc='lower left')

        fig.text(0.04, 0.5, 'Channel depth (m)', va='center',
                 rotation='vertical')
        fig.text(0.5, 0.02, 'Along channel distance (km)', ha='center')

        filename = f'{outFolder}/ssh_depth_section'
        if tidx is not None:
            filename = f'{filename}_t{tidx:03d}'
        fig.savefig(f'{filename}.png', dpi=200, format='png')
        plt.close(fig)
