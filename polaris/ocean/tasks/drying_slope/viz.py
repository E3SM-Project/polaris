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
    def __init__(self, component, indir, damping_coeffs=None,
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
        super().__init__(component=component, name='viz', indir=indir)

        self.damping_coeffs = damping_coeffs
        self.coord_type = coord_type
        self.forcing_type = forcing_type
        self.baroclinic = baroclinic

        self.add_input_file(
            filename='mesh.nc',
            target='../../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../../init/initial_state.nc')
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
        vmax_velocity = np.max(np.abs(ds.velocityY.values))
        for tidx in range(ds.sizes['Time']):
            plot_horiz_field(ds, ds_mesh,
                             'wettingVelocityFactor',
                             'wetting_velocity_factor_horiz_t{tidx:03g}.png',
                             t_index=tidx,
                             cell_mask=cell_mask, vmin=0, vmax=1)
            ds_transect = compute_transect(x, y, ds_mesh.isel(Time=tidx),
                                           spherical=False)
            plot_transect(
                ds_transect,
                mpas_field=ds.layerThickness.isel(Time=tidx),
                out_filename=f'layer_thickness_depth_t{tidx:03g}.png',
                title='layer thickness',
                colorbar_label=r'm', cmap='cmo.thermal')
            plot_transect(
                ds_transect,
                mpas_field=ds.velocityY.isel(Time=tidx),
                out_filename=f'velocityY_depth_t{tidx:03g}.png',
                title='along-slope velocity',
                vmin=-vmax_velocity, vmax=vmax_velocity,
                colorbar_label='m/s', cmap='cmo.balance')
            if self.baroclinic:
                plot_transect(
                    ds_transect,
                    mpas_field=ds.salinity.isel(Time=tidx),
                    out_filename=f'salinity_depth_t{tidx:03g}.png',
                    title='salinity',
                    colorbar_label=r'PSU', cmap='cmo.haline')
                plot_transect(
                    ds_transect,
                    mpas_field=ds.wettingVelocityBaroclinic.isel(Time=tidx),
                    out_filename=f'baroclinic_factor_depth_t{tidx:03g}.png',
                    title='baroclinic factor', vmin=0, vmax=1,
                    colorbar_label=r'', cmap='cmo.thermal')
        if self.damping_coeffs is not None:
            self._plot_ssh_validation()
        else:
            for tidx in range(ds.sizes['time']):
                plot_horiz_field(ds, ds_mesh,
                                 'ssh',
                                 'ssh_horiz_t{tidx:03g}.png',
                                 t_index=tidx,
                                 cell_mask=cell_mask)
        if self.baroclinic:
            for tidx in range(ds.sizes['time']):
                plot_horiz_field(
                    ds, ds_mesh,
                    'wettingVelocityBarotropicSubcycle',
                    'wettingVelocityBarotropicSubcycle_horiz_t{tidx:03g}.png',
                    t_index=tidx,
                    cell_mask=cell_mask, vmin=0, vmax=1)
            self._plot_salinity(tidx=-1, y_distance=45.)

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
        if damping_coeffs is None:
            naxes = 1
            ncFilename = ['output.nc']
        else:
            naxes = len(damping_coeffs)
            ncFilename = [f'output_{damping_coeff}.nc'
                          for damping_coeff in damping_coeffs]
        fig, _ = plt.subplots(nrows=naxes, ncols=1, figsize=figsize, dpi=100)

        for i in range(naxes):
            ax = plt.subplot(naxes, 1, i + 1)
            ds = xr.open_dataset(ncFilename[i])
            ympas = ds.ssh.where(ds.tidalInputMask).mean('nCells').values
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
