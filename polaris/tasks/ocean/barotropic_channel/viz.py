import cmocean  # noqa: F401
import xarray as xr

from polaris import Step

# from polaris.mpas import cell_mask_to_edge_mask
from polaris.viz import plot_horiz_field


class Viz(Step):
    """
    A step for plotting the results of a series of baroclinic channel RPE runs
    """

    def __init__(self, component, indir):
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
        self.add_input_file(
            filename='mesh.nc', target='../init/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', target='../init/initial_state.nc'
        )
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
        )

    def run(self):
        """
        Run this step of the task
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        ds_init = xr.load_dataset('init.nc')
        ds_out = xr.load_dataset('output.nc')

        cell_mask = ds_init.maxLevelCell >= 1

        vmax = 0.1
        # vmax = np.max(np.abs(ds_init.normalVelocity.values))

        # Uncomment these lines to get 10 evenly spaced time slices
        # nt = ds_out.sizes['Time']
        # for t_index in np.arange(0, nt, int(np.floor(nt / 10))):

        # These indices correspond to the first and last time step
        for t_index in [0, -1]:
            ds = ds_out.isel(Time=t_index)
            plot_horiz_field(
                ds_mesh,
                ds['velocityZonal'],
                f'velocity_zonal_t{t_index}.png',
                vmin=-vmax,
                vmax=vmax,
                cmap='cmo.balance',
                field_mask=cell_mask,
            )
            plot_horiz_field(
                ds_mesh,
                ds['velocityMeridional'],
                f'velocity_meridional_t{t_index}.png',
                vmin=-vmax,
                vmax=vmax,
                cmap='cmo.balance',
                field_mask=cell_mask,
            )
