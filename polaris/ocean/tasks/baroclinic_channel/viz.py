import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.viz import compute_transect, plot_transect
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
            filename='mesh.nc',
            target='../../init/culled_mesh.nc')
        self.add_input_file(
            filename='init.nc',
            target='../../init/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the task
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        ds_init = xr.load_dataset('init.nc')
        ds = xr.load_dataset('output.nc')
        t_index = ds.sizes['Time'] - 1
        cell_mask = ds_init.maxLevelCell >= 1
        max_velocity = np.max(np.abs(ds.normalVelocity.values))
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'final_normalVelocity.png',
                         t_index=t_index,
                         vmin=-max_velocity, vmax=max_velocity,
                         cmap='cmo.balance', show_patch_edges=True,
                         cell_mask=cell_mask)

        x_cell = ds_mesh.xCell
        y_cell = ds_mesh.yCell

        x_min = x_cell.min().values
        x_max = x_cell.max().values
        y_min = y_cell.min().values
        y_max = y_cell.max().values

        x_mid = 0.5 * (x_min + x_max)

        y = xr.DataArray(data=np.linspace(y_min, y_max, 2), dims=('nPoints',))
        x = x_mid * xr.ones_like(y)

        ds_transect = compute_transect(x=x, y=y,
                                       ds_3d_mesh=ds_init.isel(Time=0),
                                       spherical=False)

        field_name = 'temperature'
        mpas_field = ds[field_name].isel(Time=t_index)
        plot_transect(ds_transect=ds_transect, mpas_field=mpas_field,
                      title=f'{field_name} at x={1e-3 * x_mid:.1f} km',
                      out_filename=f'final_{field_name}_section.png',
                      vmin=9., vmax=13., cmap='cmo.thermal',
                      colorbar_label=r'$^\circ$C')

        plot_horiz_field(ds, ds_mesh, 'temperature', 'final_temperature.png',
                         t_index=t_index, vmin=9., vmax=13.,
                         cmap='cmo.thermal', cell_mask=cell_mask, transect_x=x,
                         transect_y=y)
