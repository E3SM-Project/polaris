import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.rpe import compute_rpe


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
            filename='initial_state.nc',
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
        section = self.config['baroclinic_channel']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        init_filename = self.inputs[0]
        rpe = compute_rpe(initial_state_file_name=init_filename,
                          output_files=self.inputs[1:])
        with xr.open_dataset(init_filename) as ds_init:
            nx = ds_init.attrs['nx']
            ny = ds_init.attrs['ny']
        _plot(nx, ny, lx, ly, self.outputs[0], self.nus, rpe)


def _plot(nx, ny, lx, ly, filename, nus, rpe):
    """
    Plot section of the baroclinic channel at different viscosities

    Parameters
    ----------
    nx : int
        The number of cells in the x direction

    ny : int
        The number of cells in the y direction (before culling)

    lx : float
        The size of the domain in km in the x direction

    ly : int
        The size of the domain in km in the y direction

    filename : str
        The output file name

    nus : list
        The viscosity values

    rpe : numpy.ndarray
        The reference potential energy with size len(nu) x len(time)
    """

    plt.switch_backend('Agg')
    num_files = len(nus)
    time = 20

    ds = xr.open_dataset(f'output_nu_{nus[0]:g}.nc', decode_times=False)
    times = ds.daysSinceStartOfSim.values

    fig = plt.figure()
    for i in range(num_files):
        rpe_norm = np.divide((rpe[i, :] - rpe[i, 0]), rpe[i, 0])
        plt.plot(times, rpe_norm,
                 label=f"$\\nu_h=${nus[i]}")
    plt.xlabel('Time, days')
    plt.ylabel('RPE-RPE(0)/RPE(0)')
    plt.legend()
    plt.savefig('rpe_t.png')
    plt.close(fig)

    fig, axs = plt.subplots(1, num_files, figsize=(
        2.1 * num_files, 5.0), constrained_layout=True)

    # ***NOTE***: This is a quick-and-dirty plotting technique for regular
    # planar hex meshes that we do not recommend adopting in other tasks
    for iCol, nu in enumerate(nus):
        ds = xr.open_dataset(f'output_nu_{nu:g}.nc', decode_times=False)
        times = ds.daysSinceStartOfSim.values
        time_index = np.argmin(np.abs(times - time))
        var = ds.temperature.values
        var1 = np.reshape(var[time_index, :, 0], [ny, nx])
        # flip in y-dir
        var = np.flipud(var1)

        # Every other row in y needs to average two neighbors in x on
        # planar hex mesh
        var_avg = var
        for j in range(0, ny, 2):
            for i in range(1, nx - 2):
                var_avg[j, i] = (var[j, i + 1] + var[j, i]) / 2.0

        ax = axs[iCol]
        dis = ax.imshow(
            var_avg,
            extent=[0, lx, 0, ly],
            cmap='cmo.thermal',
            vmin=11.8,
            vmax=13.0)
        ax.set_title(f'day {times[time_index]}, '
                     f'$\\nu_h=${nus[iCol]}')
        ax.set_xticks(np.linspace(0, lx, 5))
        ax.set_yticks(np.arange(0, ly, 11))

        ax.set_xlabel('x, km')
        if iCol == 0:
            ax.set_ylabel('y, km')
        if iCol == num_files - 1:
            fig.colorbar(dis, ax=axs[num_files - 1], aspect=40)
    plt.savefig(filename)
