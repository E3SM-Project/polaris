import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.mpas import time_since_start
from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class Viz(OceanIOStep):
    """
    A step for visualizing the output of the default merry-go-round test case
    """

    def __init__(self, component, dependencies, taskdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        dependencies : dict of polaris.steps
            the dependencies of this step must be given as separate keys in the
            dict:

                mesh : polaris.step
                    must have the attribute `path`, the path to `base_mesh.nc`
                    for the default resolution
                init : polaris.step
                    must have the attribute `path`, the path to
                    `initial_state.nc` for the default resolution
                forward : dict of polaris.steps
                    must have the attribute `path`, the path to `forward.nc`
                    for the default resolution

        taskdir : str
            The subdirectory that the task belongs to
        """
        super().__init__(component=component, name='viz', indir=taskdir)
        self.dependencies_dict = dependencies
        self.add_output_file('merry_go_round_section.png')

    def setup(self):
        """
        Add input files, which are dependent on the config options values
        """
        super().setup()
        dependencies = self.dependencies_dict

        base_mesh = dependencies['mesh']
        init = dependencies['init']
        forward = dependencies['forward']

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/culled_mesh.nc',
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/init.nc',
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc',
        )
        self.add_input_file(
            filename='output.nc',
            work_dir_target=f'{forward.path}/output.nc',
        )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        config = self.config

        model = config.get('ocean', 'model')
        section = config['merry_go_round']

        use_mplstyle()
        fig, axes = plt.subplots(
            nrows=2,
            ncols=2,
            figsize=(8, 5),
            constrained_layout=True,
            sharex=True,
            sharey=True,
        )

        section = config['convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_hour = 3600.0
        time = eval_time * s_per_hour

        ds_mesh = self.open_model_dataset('mesh.nc', config)
        ds_init = self.open_model_dataset('init.nc', config)
        ds_vert_coord = self.open_vert_coord_dataset(ds_init)
        ds = self.open_model_dataset('output.nc', config, mesh_filename='mesh.nc', vert_filename='vert_coord.nc', decode_times=False)

        x_min = ds_mesh.xVertex.min().values
        x_max = ds_mesh.xVertex.max().values
        y_mid = ds_mesh.yCell.median().values

        x = xr.DataArray(data=np.linspace(x_min, x_max, 2), dims=('nPoints',))
        y = y_mid * xr.ones_like(x)

        if model == 'mpas-o':
            dt = time_since_start(ds.xtime.values)
        else:
            # time is seconds since the start of the simulation in Omega
            dt = ds.Time.values
        tidx = np.argmin(np.abs(dt - time))

        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_init.layerThickness.isel(Time=0),
            bottom_depth=ds_vert_coord.bottomDepth,
            min_level_cell=ds_vert_coord.minLevelCell - 1,
            max_level_cell=ds_vert_coord.maxLevelCell - 1,
            spherical=False,
        )

        vert_velocity = ds.vertVelocityTop.isel(Time=tidx)
        if 'nVertLevelsP1' in vert_velocity.dims:
            vert_velocity = vert_velocity.isel(nVertLevelsP1=slice(0, -1))
        tracer_exact = ds_init.tracer1.isel(Time=0)
        tracer_model = ds.tracer1.isel(Time=tidx)
        tracer_error = tracer_model - tracer_exact

        data_min = np.min(np.abs(tracer_exact.values))
        data_max = np.max(np.abs(tracer_exact.values))
        error_range = np.max(np.abs(tracer_error.values))

        if 'velocityX' in ds.keys():
            horz_velocity = ds.velocityX.isel(Time=tidx)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=horz_velocity,
                ax=axes[0, 0],
                vmin=-0.008,
                vmax=0.008,
                cmap='cmo.balance',
                colorbar_label='horizontal velocity',
                color_start_and_end=False,
            )

        print('shape vert_velocity', vert_velocity.sizes)
        #IndexError: index 50 is out of bounds for axis 1 with size 50
        #  File "/lcrc/group/e3sm/ac.cbegeman/scratch/polaris-repo/fixup-pseudo-omega-support/fixup-pseudo/.pixi/envs/default/lib/python3.14/site-packages/mpas_tools/ocean/viz/transect/plot.py", line 138, in plot_transect
        #    transect_field = interp_mpas_to_transect_cells(
        #        ds_transect, mpas_field
        #    )
        #  File "/lcrc/group/e3sm/ac.cbegeman/scratch/polaris-repo/fixup-pseudo-omega-support/fixup-pseudo/.pixi/envs/default/lib/python3.14/site-packages/mpas_tools/ocean/viz/transect/vert.py", line 275, in interp_mpas_to_transect_cells
        #    da_cells = da.isel(
        #        nCells=cell_indices, nVertLevelsP1=intreface_indices
        #    )
        # or
        #          File "/lcrc/group/e3sm/ac.cbegeman/scratch/polaris-repo/fixup-pseudo-omega-support/fixup-pseudo/.pixi/envs/default/lib/python3.14/site-packages/mpas_tools/ocean/viz/transect/plot.py", line 150, in plot_transect
        #    pc = ax.pcolormesh(
        #        x.values,
        #    ...<6 lines>...
        #        zorder=0,
        #    )
        #ValueError: For X (101) and Y (401) with flat shading, A should have shape (400, 100, 3) or (400, 100, 4) or (400, 100) or (40000,), not (400, 100, 51)
        plot_transect(
            ds_transect=ds_transect,
            mpas_field=vert_velocity,
            ax=axes[0, 1],
            vmin=-0.02,
            vmax=0.02,
            cmap='cmo.balance',
            colorbar_label='vertical velocity',
            color_start_and_end=False,
        )

        plot_transect(
            ds_transect=ds_transect,
            mpas_field=tracer_exact,
            ax=axes[1, 0],
            vmin=data_min,
            vmax=data_max,
            cmap='cmo.thermal',
            colorbar_label='tracer1 at t=0',
            color_start_and_end=False,
        )

        plot_transect(
            ds_transect=ds_transect,
            mpas_field=tracer_error,
            ax=axes[1, 1],
            vmin=-error_range,
            vmax=error_range,
            cmap='cmo.curl',
            colorbar_label=f'delta(tracer1) at t={eval_time:g}h',
            color_start_and_end=False,
        )

        axes[0, 0].set_xlabel(None)
        axes[0, 1].set_xlabel(None)

        axes[0, 1].set_ylabel(None)
        axes[1, 1].set_ylabel(None)

        fig.savefig(
            'merry_go_round_section.png', bbox_inches='tight', pad_inches=0.1
        )
