import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.rpe import compute_rpe
from polaris.ocean.viz import compute_transect, plot_transect
from polaris.viz import use_mplstyle


class Analysis(Step):
    """
    A step for plotting the results of a series of baroclinic channel RPE runs

    Attributes
    ----------
    nus : list
        A list of viscosities
    """
    def __init__(self, component, indir, nus):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended

        nus : list of float
            A list of viscosities
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.nus = nus

        self.add_input_file(
            filename='mesh.nc',
            target='../../../init/culled_mesh.nc')

        self.add_input_file(
            filename='init.nc',
            target='../../../init/initial_state.nc')

        for nu in nus:
            self.add_input_file(
                filename=f'output_nu_{nu:g}.nc',
                target=f'../nu_{nu:g}/output.nc')

        self.add_output_file(
            filename='sections_internal_wave.png')
        self.add_output_file(filename='rpe_t.png')
        self.add_output_file(filename='rpe.csv')

    def run(self):
        """
        Run this step of the test case
        """
        mesh_filename = 'mesh.nc'
        init_filename = 'init.nc'
        output_filename = self.outputs[0]
        nus = self.nus
        section = self.config['internal_wave_rpe']

        rpe = compute_rpe(mesh_filename=mesh_filename,
                          initial_state_filename=init_filename,
                          output_filenames=self.inputs[2:])

        plt.switch_backend('Agg')
        sim_count = len(nus)
        time = section.getfloat('plot_time')
        min_temp = section.getfloat('min_temp')
        max_temp = section.getfloat('max_temp')

        ds = xr.open_dataset(f'output_nu_{nus[0]:g}.nc', decode_times=False)
        times = ds.daysSinceStartOfSim.values

        use_mplstyle()
        fig = plt.figure()
        for i in range(sim_count):
            rpe_norm = np.divide((rpe[i, :] - rpe[i, 0]), rpe[i, 0])
            plt.plot(times, rpe_norm, label=f'$\\nu_h=${nus[i]}')
        plt.xlabel('Time, days')
        plt.ylabel('RPE-RPE(0)/RPE(0)')
        plt.legend()
        plt.savefig('rpe_t.png')
        plt.close(fig)

        ds_mesh = xr.open_dataset(mesh_filename)
        ds_init = xr.open_dataset(init_filename)

        fig, axes = plt.subplots(1, sim_count, sharey=True,
                                 figsize=(3 * sim_count, 5.0),
                                 constrained_layout=True)
        fig.suptitle(f'day {time}')
        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))
        for row_index, nu in enumerate(nus):
            ax = axes[row_index]
            ds = xr.open_dataset(f'output_nu_{nu:g}.nc', decode_times=False)
            times = ds.daysSinceStartOfSim.values
            time_index = np.argmin(np.abs(times - time))
            ds_transect = compute_transect(
                x=x, y=y, ds_horiz_mesh=ds_mesh,
                layer_thickness=ds.layerThickness.isel(Time=time_index),
                bottom_depth=ds_init.bottomDepth,
                min_level_cell=ds_init.minLevelCell - 1,
                max_level_cell=ds_init.maxLevelCell - 1,
                spherical=False)

            if row_index == len(nus) - 1:
                colorbar_label = r'$^{\circ}$C'
            else:
                colorbar_label = None
            plot_transect(ds_transect,
                          mpas_field=ds.temperature.isel(Time=time_index),
                          ax=ax,
                          title='temperature',
                          interface_color='grey',
                          vmin=min_temp, vmax=max_temp,
                          colorbar_label=colorbar_label, cmap='cmo.thermal')
            ax.set_title(f'$\\nu_h=${nu:g}')
            if row_index != 0:
                ax.set_ylabel(None)
        plt.savefig(output_filename)
