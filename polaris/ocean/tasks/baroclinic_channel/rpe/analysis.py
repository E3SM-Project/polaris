import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.rpe import compute_rpe
from polaris.viz import plot_horiz_field, use_mplstyle


class Analysis(Step):
    """
    A step for plotting the results of a series of baroclinic channel RPE runs

    Attributes
    ----------
    nus : list
        A list of viscosities
    """
    def __init__(self, component, indir, resolution, nus):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended

        resolution : float
            The resolution of the test case in km

        nus : list of float
            A list of viscosities
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.nus = nus

        self.add_input_file(
            filename='mesh.nc',
            target='../../init/culled_mesh.nc')

        self.add_input_file(
            filename='init.nc',
            target='../../init/initial_state.nc')

        for nu in nus:
            self.add_input_file(
                filename=f'output_nu_{nu:g}.nc',
                target=f'../nu_{nu:g}/output.nc')

        self.add_output_file(
            filename=f'sections_baroclinic_channel_{resolution}.png')
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
        section = self.config['baroclinic_channel_rpe']

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

        fig, axes = plt.subplots(1, sim_count, figsize=(
            3 * sim_count, 5.0), constrained_layout=True)

        for row_index, nu in enumerate(nus):
            ax = axes[row_index]
            ds = xr.open_dataset(f'output_nu_{nu:g}.nc', decode_times=False)
            ds = ds.isel(nVertLevels=0)
            times = ds.daysSinceStartOfSim.values
            time_index = np.argmin(np.abs(times - time))

            cell_mask = ds_init.maxLevelCell >= 1
            plot_horiz_field(ds_mesh, ds['temperature'], ax=ax,
                             cmap='cmo.thermal', t_index=time_index,
                             vmin=min_temp, vmax=max_temp,
                             cmap_title='SST (C)', field_mask=cell_mask)
            ax.set_title(f'day {times[time_index]:g}, $\\nu_h=${nu:g}')

        plt.savefig(output_filename)
