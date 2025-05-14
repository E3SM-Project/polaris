import os

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris import Step
from polaris.viz import plot_horiz_field
from polaris.viz.style import use_mplstyle


class Viz(Step):
    """
    A step for plotting the results of a series of drying_slope runs

    Attributes
    ----------
    damping_coeffs : list of float
        The damping coefficients that correspond to each forward run to be
        plotted

    coord_type : str, optional
        The vertical coordinate type

    forcing_type : str, optional
        The forcing type to apply at the "tidal" boundary as a namelist
        option

    baroclinic : logical
        Whether this test case is the baroclinic version

    times : list of float
        The solution times at which to plot

    datatypes : list of str
        The datatypes to plot
    """

    def __init__(
        self,
        component,
        indir=None,
        subdir=None,
        name='viz',
        damping_coeffs=None,
        coord_type='sigma',
        baroclinic=False,
        forcing_type='tidal_cycle',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended

        damping_coeffs : list of float
            The damping coefficients that correspond to each forward run to be
            plotted

        coord_type : str, optional
            The vertical coordinate type

        forcing_type : str, optional
            The forcing type to apply at the "tidal" boundary as a namelist
            option

        baroclinic : logical
            Whether this test case is the baroclinic version
        """
        super().__init__(
            component=component, name=name, indir=indir, subdir=subdir
        )

        self.damping_coeffs = damping_coeffs
        self.coord_type = coord_type
        self.forcing_type = forcing_type
        self.baroclinic = baroclinic
        self.times = ['0.05', '0.15', '0.25', '0.30', '0.40', '0.50']
        self.datatypes = ['analytical', 'ROMS']

        self.add_input_file(
            filename='mesh.nc', target='../init/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', target='../init/initial_state.nc'
        )
        self.add_input_file(filename='forcing.nc', target='../init/forcing.nc')
        if damping_coeffs is None:
            self.add_input_file(
                filename='output.nc', target='../forward/output.nc'
            )
        else:
            for damping_coeff in damping_coeffs:
                self.add_input_file(
                    filename=f'output_{damping_coeff:03g}.nc',
                    target=f'../forward_{damping_coeff:03g}/output.nc',
                )
            for time in self.times:
                for datatype in self.datatypes:
                    for damping_coeff in damping_coeffs:
                        filename = (
                            f'r{damping_coeff}d{time}-{datatype.lower()}.csv'
                        )
                        self.add_input_file(
                            filename=filename,
                            target=filename,
                            database='drying_slope',
                        )

    def run(self):
        """
        Run this step of the task
        """
        use_mplstyle()
        ds_forcing = xr.open_dataset('forcing.nc')
        self._plot_ssh_time_series(
            ds_forcing=ds_forcing, forcing_type=self.forcing_type
        )

        if not self.baroclinic:
            self._plot_ssh_validation()

        ds_mesh = xr.load_dataset('init.nc')
        cell_mask = ds_mesh.maxLevelCell >= 1
        cellsOnEdge1 = ds_mesh.cellsOnEdge.isel(TWO=0)
        cellsOnEdge2 = ds_mesh.cellsOnEdge.isel(TWO=1)
        cell1_is_valid = cell_mask[cellsOnEdge1 - 1].values == 1
        cell2_is_valid = cell_mask[cellsOnEdge2 - 1].values == 1
        edge_mask = xr.where(
            np.logical_and(cell1_is_valid, cell2_is_valid), 1, 0
        )

        out_filenames = []
        if not self.damping_coeffs:
            out_filenames.append('output.nc')
        else:
            for damping_coeff in self.damping_coeffs:
                out_filenames.append(f'output_{damping_coeff:03g}.nc')

        for out_filename in out_filenames:
            ds = xr.load_dataset(out_filename)
            x, y = self._plot_transects(ds_mesh=ds_mesh, ds=ds)

            for atime in self.times:
                # Plot MPAS-O data
                mpastime = ds.daysSinceStartOfSim.values
                simtime = pd.to_timedelta(mpastime)
                s_day = 86400.0
                time = simtime.total_seconds()
                tidx = np.argmin(np.abs(time / s_day - float(atime)))
                plot_horiz_field(
                    ds_mesh,
                    ds.wettingVelocityFactor,
                    cmap_title=r'$\Phi$',
                    out_file_name=f'wetting_factor_t{tidx:03g}.png',
                    transect_x=x,
                    transect_y=y,
                    show_patch_edges=True,
                    t_index=tidx,
                    field_mask=edge_mask,
                    vmin=0,
                    vmax=1,
                )

                plot_horiz_field(
                    ds_mesh,
                    ds.upwindFactor,
                    cmap_title=r'$\Psi$',
                    out_file_name=f'upwind_factor_t{tidx:03g}.png',
                    transect_x=x,
                    transect_y=y,
                    show_patch_edges=False,
                    t_index=tidx,
                    field_mask=edge_mask,
                    vmin=0,
                    vmax=1,
                )

                if self.baroclinic:
                    plot_horiz_field(
                        ds_mesh,
                        ds.wettingVelocityBarotropicSubcycle,
                        cmap_title=r'$\Phi_{btr}$',
                        out_file_name=f'wetting_barotropic_t{tidx:03g}.png',
                        t_index=tidx,
                        field_mask=edge_mask,
                        vmin=0,
                        vmax=1,
                    )
                    self._plot_salinity(tidx=-1, y_distance=45.0)

                plot_horiz_field(
                    ds_mesh,
                    ds.ssh,
                    cmap_title='SSH',
                    out_file_name=f'ssh_horiz_t{tidx:03g}.png',
                    t_index=tidx,
                    field_mask=cell_mask,
                )

    def _plot_transects(self, ds_mesh, ds):
        # Note: capability currently only works for cell-centered quantities

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
        time_hours = simtime.total_seconds() / 3600.0
        for tidx in range(ds.sizes['Time']):
            ds_transect = compute_transect(
                x=x,
                y=y,
                ds_horiz_mesh=ds_mesh,
                layer_thickness=ds.layerThickness.isel(Time=tidx),
                bottom_depth=ds.bottomDepth,
                min_level_cell=ds.minLevelCell - 1,
                max_level_cell=ds.maxLevelCell - 1,
                spherical=False,
            )

            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.velocityX.isel(Time=tidx),
                title='Across-slope velocity',
                out_filename=f'velocityX_depth_t{tidx:03g}.png',
                vmin=-vmax_velocity,
                vmax=vmax_velocity,
                colorbar_label=r'',
                cmap='cmo.balance',
            )

            fig, axs = plt.subplots(nrows, sharex=True, figsize=(5, 3 * nrows))
            fig.suptitle(f'Time: {time_hours[tidx]:2.1f} hours')
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.layerThickness.isel(Time=tidx),
                ax=axs[0],
                outline_color=None,
                ssh_color='blue',
                seafloor_color='black',
                interface_color='grey',
                vmin=vmin_layer_thickness,
                vmax=vmax_layer_thickness,
                colorbar_label=r'm',
                cmap='cmo.thermal',
            )
            axs[0].set_title('Layer thickness')
            axs[0].set_ylim([ymin, ymax])
            axs[0].set_xlabel(None)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds.velocityY.isel(Time=tidx),
                ax=axs[1],
                outline_color=None,
                ssh_color='blue',
                seafloor_color='black',
                vmin=-vmax_velocity,
                vmax=vmax_velocity,
                colorbar_label='m/s',
                cmap='cmo.balance',
            )
            axs[1].set_title('Along-slope velocity')
            axs[1].set_ylim([ymin, ymax])
            axs[1].set_xlabel(None)
            if self.baroclinic:
                plot_transect(
                    ds_transect=ds_transect,
                    mpas_field=ds.salinity.isel(Time=tidx),
                    ax=axs[2],
                    outline_color=None,
                    ssh_color='blue',
                    seafloor_color='black',
                    vmin=vmin_salinity,
                    vmax=vmax_salinity,
                    colorbar_label=r'PSU',
                    cmap='cmo.haline',
                )
                axs[2].set_title('Salinity')
                axs[2].set_ylim([ymin, ymax])
            plt.savefig(
                f'layerThickness_velocityY_depth_t{tidx:03g}.png',
                bbox_inches='tight',
            )
            plt.close()

        return x, y

    def _forcing(self, t):
        ssh = 10.0 * np.sin(t * np.pi / 12.0) - 10.0
        return ssh

    def _plot_salinity(self, tidx=None, y_distance=0.0, outFolder='.'):
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

    def _plot_ssh_time_series(
        self, ds_forcing, outFolder='.', forcing_type='tidal_cycle'
    ):
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
            ncFilename = [
                f'output_{damping_coeff}.nc'
                for damping_coeff in damping_coeffs
            ]
        fig, _ = plt.subplots(nrows=naxes, ncols=1, figsize=figsize, dpi=100)

        mask = ds_forcing.tidalInputMask
        for i in range(naxes):
            ax = plt.subplot(naxes, 1, i + 1)
            ds = xr.open_dataset(ncFilename[i])
            ympas = ds.ssh.where(mask).mean('nCells').values
            xmpas = np.linspace(0, 1.0, len(ds.xtime)) * 12.0
            ax.plot(
                xmpas, ympas, marker='o', label='MPAS-O forward', color='k'
            )
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
        colors = {'MPAS-O': 'k', 'analytical': 'b', 'ROMS': 'g'}

        locs = [7.2, 2.2, 0.2, 1.2, 4.2, 9.3]
        locs = 0.92 - np.divide(locs, 11.0)

        damping_coeffs = self.damping_coeffs

        if damping_coeffs is None:
            raise ValueError(
                'ssh validation is only supported for damping'
                'coefficient comparison'
            )
        naxes = len(damping_coeffs)
        nhandles = len(datatypes) + 1

        ds_mesh = xr.open_dataset('init.nc')
        # Note: capability currently only works for cell-centered quantities

        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))
        ymin = -ds_mesh.bottomDepth.max()

        section = self.config['drying_slope_barotropic']
        drying_length = section.getfloat('ly_analysis')
        # we need to add x_offset to observational datasets
        x_offset = y_min.values / 1000.0
        s_day = 86400.0

        for _, atime in enumerate(self.times):
            fig, axs = plt.subplots(
                nrows=naxes, ncols=1, sharex=True, figsize=(5, 3 * naxes)
            )
            fig.suptitle(f'Time: {float(atime) * 24.0:2.1f} hours')
            for i, damping_coeff in enumerate(self.damping_coeffs):
                ds = xr.load_dataset(f'output_{damping_coeff:03g}.nc')
                # Plot MPAS-O data
                mpastime = ds.daysSinceStartOfSim.values
                simtime = pd.to_timedelta(mpastime)
                time = simtime.total_seconds()
                tidx = np.argmin(np.abs(time / s_day - float(atime)))
                ds_transect = compute_transect(
                    x=x,
                    y=y,
                    ds_horiz_mesh=ds_mesh,
                    layer_thickness=ds.layerThickness.isel(Time=tidx),
                    bottom_depth=ds.bottomDepth,
                    min_level_cell=ds.minLevelCell - 1,
                    max_level_cell=ds.maxLevelCell - 1,
                    spherical=False,
                )
                plot_transect(
                    ds_transect=ds_transect,
                    mpas_field=None,
                    ax=axs[i],
                    outline_color=None,
                    ssh_color='blue',
                    seafloor_color='black',
                )
                ymax = ds.ssh.max()
                axs[i].set_xlim([x_offset, drying_length + x_offset])
                axs[i].set_ylim([ymin.values, ymax.values])
                if i == naxes - 1:
                    axs[i].set_xlabel('Along channel distance (km)')
                else:
                    axs[i].set_xlabel(None)

                axs[i].set_title('r = ' + str(damping_coeffs[i]))
                for datatype in datatypes:
                    datafile = (
                        f'./r{damping_coeffs[i]}d{atime}-'
                        f'{datatype.lower()}.csv'
                    )
                    if os.path.exists(datafile):
                        data = pd.read_csv(datafile, header=None)
                        axs[i].scatter(
                            data[0] + x_offset,
                            -data[1],
                            marker='.',
                            color=colors[datatype],
                            label=datatype,
                        )
                ds.close()

                h, l0 = axs[i].get_legend_handles_labels()
                axs[i].legend(
                    h[:nhandles],
                    l0[:nhandles],
                    frameon=False,
                    loc='lower left',
                )

            filename = f'{outFolder}/ssh_depth_section_t{tidx:03d}'
            fig.savefig(f'{filename}.png', dpi=200, format='png')
            plt.close(fig)
