import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.mpas import cell_mask_to_edge_mask
from polaris.ocean.model import OceanIOStep
from polaris.viz import plot_horiz_field


class Viz(OceanIOStep):
    """
    A step for plotting the results of a series of baroclinic channel RPE runs

    Attributes
    ----------
    dependencies_dict : dict of polaris.Steps
        The dependencies of this step must be given as separate keys in the
        dict:

            mesh : polaris.Step
                Must have the attribute `path`, the path to `culled_mesh.nc`

            init : polaris.Step
                Must have the attribute `path`, the path to `init.nc`

            forward : polaris.Step
                Must have the attribute `path`, the path to `output.nc`
    """

    def __init__(self, component, dependencies, taskdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        dependencies : dict of polaris.Steps
            The dependencies of this step must be given as separate keys in the
            dict:

                mesh : polaris.Step
                    Must have the attribute `path`, the path to
                    `culled_mesh.nc`

                init : polaris.Step
                    Must have the attribute `path`, the path to `init.nc`

                forward : polaris.Step
                    Must have the attribute `path`, the path to `output.nc`

        taskdir : str
            The subdirectory that the task belongs to
        """
        super().__init__(component=component, name='viz', indir=taskdir)
        self.dependencies_dict = dependencies

    def setup(self):
        """
        Add input files from dependencies
        """

        super().setup()
        dependencies = self.dependencies_dict

        mesh = dependencies['mesh']
        init = dependencies['init']
        forward = dependencies['forward']

        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{mesh.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )
        if self.component.model == 'omega':
            self.add_input_file(
                filename='vert_coord.nc',
                work_dir_target=f'{init.path}/vert_coord.nc',
            )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        ds_mesh = self.open_model_dataset('mesh.nc', config=config)
        ds_init = self.open_model_dataset('init.nc', config=config)
        if self.component.model == 'omega':
            ds_vert = self.open_model_dataset('vert_coord.nc', config=config)
        else:
            ds_vert = ds_init
        ds = self.open_model_dataset('output.nc', config=config)

        t_index = ds.sizes['Time'] - 1
        cell_mask = ds_vert.maxLevelCell >= 1
        edge_mask = cell_mask_to_edge_mask(ds_mesh, cell_mask)
        max_velocity = np.max(np.abs(ds.normalVelocity.values))

        step = 10
        for t_index in range(0, ds.sizes['Time'], step):
            plot_horiz_field(
                ds_mesh,
                ds['normalVelocity'],
                f'normalVelocity_{t_index:04}.png',
                t_index=t_index,
                vmin=-max_velocity,
                vmax=max_velocity,
                cmap='cmo.balance',
                show_patch_edges=True,
                field_mask=edge_mask,
            )

            y_min = ds_mesh.yVertex.min().values
            y_max = ds_mesh.yVertex.max().values
            x_mid = ds_mesh.xCell.median().values

            y = xr.DataArray(
                data=np.linspace(y_min, y_max, 2), dims=('nPoints',)
            )
            x = x_mid * xr.ones_like(y)

            ds_transect = compute_transect(
                x=x,
                y=y,
                ds_horiz_mesh=ds_mesh,
                layer_thickness=ds.layerThickness.isel(Time=t_index),
                bottom_depth=ds_vert.bottomDepth,
                min_level_cell=ds_vert.minLevelCell - 1,
                max_level_cell=ds_vert.maxLevelCell - 1,
                spherical=False,
            )

            field_name = 'temperature'
            vmin = ds[field_name].min().values
            vmax = ds[field_name].max().values
            mpas_field = ds[field_name].isel(Time=t_index)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=mpas_field,
                title=f'{field_name} at x={1e-3 * x_mid:.1f} km',
                out_filename=f'{field_name}_section_{t_index:04}.png',
                vmin=vmin,
                vmax=vmax,
                cmap='cmo.thermal',
                colorbar_label=r'$^\circ$C',
                color_start_and_end=True,
            )

            plot_horiz_field(
                ds_mesh,
                ds['temperature'],
                f'temperature_{t_index:04}.png',
                t_index=t_index,
                vmin=vmin,
                vmax=vmax,
                cmap='cmo.thermal',
                field_mask=cell_mask,
                transect_x=x,
                transect_y=y,
            )
