import cmocean  # noqa: F401
import numpy as np

from polaris.ocean.model import OceanIOStep

# from polaris.mpas import cell_mask_to_edge_mask
from polaris.viz import plot_horiz_field


class Viz(OceanIOStep):
    """
    A step for plotting the results of barotropic channel forward step
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
        ds_mesh = self.open_model_dataset('mesh.nc')
        ds_init = self.open_model_dataset('init.nc')
        ds_out = self.open_model_dataset('output.nc')

        cell_mask = ds_init.maxLevelCell >= 1
        vertex_mask = ds_init.boundaryVertex == 0

        # Uncomment these lines to get 10 evenly spaced time slices
        # nt = ds_out.sizes['Time']
        # for t_index in np.arange(0, nt, int(np.floor(nt / 10))):

        # These indices correspond to the first and last time step
        for t_index in [0, -1]:
            for z_index in range(ds_out.sizes['nVertLevels']):
                suffix = f't{t_index}_z{z_index}'
                ds = ds_out.isel(Time=t_index, nVertLevels=z_index)
                if (
                    'velocityZonal' in ds.keys()
                    and 'velocityZonal' in ds.keys()
                ):
                    vmax = np.max(np.abs(ds.velocityZonal.values))
                    plot_horiz_field(
                        ds_mesh,
                        ds['velocityZonal'],
                        f'velocity_zonal_{suffix}.png',
                        vmin=-vmax,
                        vmax=vmax,
                        cmap='cmo.balance',
                        field_mask=cell_mask,
                    )
                    plot_horiz_field(
                        ds_mesh,
                        ds['velocityMeridional'],
                        f'velocity_meridional_{suffix}.png',
                        vmin=-vmax,
                        vmax=vmax,
                        cmap='cmo.balance',
                        field_mask=cell_mask,
                    )

                vmax = np.max(np.abs(ds.relativeVorticity.values))
                plot_horiz_field(
                    ds_mesh,
                    ds['relativeVorticity'],
                    f'relative_vorticity_{suffix}.png',
                    vmin=-vmax,
                    vmax=vmax,
                    cmap='cmo.balance',
                    field_mask=vertex_mask,
                )

                if 'circulation' in ds.keys():
                    vmax = np.max(np.abs(ds.circulation.values))
                    plot_horiz_field(
                        ds_mesh,
                        ds['circulation'],
                        f'circulation_{suffix}.png',
                        vmin=-vmax,
                        vmax=vmax,
                        cmap='cmo.balance',
                        field_mask=vertex_mask,
                    )
