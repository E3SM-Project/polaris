import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris import Step


class Viz(Step):
    """
    A step for plotting the results of the default overflow forward step
    Similar viz is duplicated for the RPE task in its analysis step
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
            filename='mesh.nc', target='../../init/culled_mesh.nc'
        )
        self.add_input_file(filename='init.nc', target='../../init/init.nc')
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
        )

    def run(self):
        """
        Run this step of the task
        """
        ds_mesh = xr.load_dataset('mesh.nc')
        ds_init = xr.load_dataset('init.nc')
        ds = xr.load_dataset('output.nc')

        x_min = ds_mesh.xVertex.min().values
        x_max = ds_mesh.xVertex.max().values
        y_mid = ds_mesh.yCell.median().values

        x = xr.DataArray(data=np.linspace(x_min, x_max, 2), dims=('nPoints',))
        y = y_mid * xr.ones_like(x)

        t_index = 0
        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_init.layerThickness.isel(Time=t_index),
            bottom_depth=ds_init.bottomDepth,
            min_level_cell=ds_init.minLevelCell - 1,
            max_level_cell=ds_init.maxLevelCell - 1,
            spherical=False,
        )

        field_name = 'temperature'
        cellMask = ds_init.cellMask.isel(nVertLevels=0)
        mpas_field = ds_init[field_name].isel(Time=t_index)
        mpas_field_valid = ds_init[field_name].isel(nCells=cellMask == 1)
        vmin = mpas_field_valid.min().values
        vmax = mpas_field_valid.max().values
        plot_transect(
            ds_transect=ds_transect,
            mpas_field=mpas_field,
            title=f'{field_name} at y={1e-3 * y_mid:.1f} km',
            out_filename=f'init_{field_name}_section.png',
            vmin=vmin,
            vmax=vmax,
            cmap='cmo.thermal',
            colorbar_label=r'$^\circ$C',
            color_start_and_end=False,
        )

        t_index = ds.sizes['Time'] - 1
        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds.layerThickness.isel(Time=t_index),
            bottom_depth=ds_init.bottomDepth,
            min_level_cell=ds_init.minLevelCell - 1,
            max_level_cell=ds_init.maxLevelCell - 1,
            spherical=False,
        )

        field_name = 'temperature'
        mpas_field = ds[field_name].isel(Time=t_index)
        plot_transect(
            ds_transect=ds_transect,
            mpas_field=mpas_field,
            title=f'{field_name} at y={1e-3 * y_mid:.1f} km',
            out_filename=f'final_{field_name}_section.png',
            vmin=vmin,
            vmax=vmax,
            cmap='cmo.thermal',
            colorbar_label=r'$^\circ$C',
            color_start_and_end=False,
        )
