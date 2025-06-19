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
    A step for visualizing the output from the merry-go-round test case
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
        Add input files, which are dependent on based on the config options
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
            work_dir_target=f'{init.path}/initial_state.nc',
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
            figsize=(12, 8),
            constrained_layout=True,
            sharex=True,
            sharey=True,
        )

        section = config['convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_hour = 3600.0
        time = eval_time * s_per_hour

        ds_mesh = self.open_model_dataset('mesh.nc')
        ds_init = self.open_model_dataset('init.nc')
        ds = self.open_model_dataset('output.nc', decode_times=False)

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
            bottom_depth=ds_init.bottomDepth,
            min_level_cell=ds_init.minLevelCell - 1,
            max_level_cell=ds_init.maxLevelCell - 1,
            spherical=False,
        )

        horz_velocity = ds.velocityX.isel(Time=tidx)
        vert_velocity = ds.vertVelocityTop.isel(Time=tidx)

        tracer_exact = ds_init.tracer1.isel(Time=0)
        tracer_model = ds.tracer1.isel(Time=tidx)
        tracer_error = tracer_model - tracer_exact

        data_min = np.min(np.abs(tracer_exact.values))
        data_max = np.max(np.abs(tracer_exact.values))
        error_range = np.max(np.abs(tracer_error.values))

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
