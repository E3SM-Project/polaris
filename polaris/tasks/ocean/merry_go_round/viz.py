import cmocean  # noqa: F401
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

from polaris.mpas import time_since_start
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class Viz(OceanIOStep):
    """
    A step for visualizing the output from the merry-go-round test case

    Attributes
    ----------
    dependencies_dict : dict of dict of polaris.Steps
        The dependencies of this step must be given as separate keys in the
        dict:

            mesh : dict of polaris.Steps
                Keys of the dict correspond to `refinement_factors`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `base_mesh.nc` of that
                resolution
            init : dict of polaris.Steps
                Keys of the dict correspond to `refinement_factors`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `initial_state.nc` of that
                resolution
            forward : dict of polaris.Steps
                Keys of the dict correspond to `refinement_factors`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `forward.nc` of that
                resolution

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time
    """

    def __init__(self, component, dependencies, taskdir, refinement='both'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step must be given as separate keys in the
            dict:

                mesh : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `base_mesh.nc` of that
                    resolution
                init : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `initial_state.nc` of that
                    resolution
                forward : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `forward.nc` of that
                    resolution

        taskdir : str
            The subdirectory that the task belongs to

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        super().__init__(component=component, name='viz', indir=taskdir)
        self.dependencies_dict = dependencies
        self.refinement = refinement
        self.add_output_file('comparison.png')

    def setup(self):
        """
        Add input files based on resolutions, which may have been changed by
        user config options
        """
        super().setup()
        config = self.config
        dependencies = self.dependencies_dict

        if self.refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = config.getlist('convergence', option, dtype=float)

        for refinement_factor in refinement_factors:
            base_mesh = dependencies['mesh'][refinement_factor]
            init = dependencies['init'][refinement_factor]
            forward = dependencies['forward'][refinement_factor]
            self.add_input_file(
                filename=f'mesh_r{refinement_factor:02g}.nc',
                work_dir_target=f'{base_mesh.path}/culled_mesh.nc',
            )
            self.add_input_file(
                filename=f'init_r{refinement_factor:02g}.nc',
                work_dir_target=f'{init.path}/initial_state.nc',
            )
            self.add_input_file(
                filename=f'output_r{refinement_factor:02g}.nc',
                work_dir_target=f'{forward.path}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        config = self.config
        if self.refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = config.getlist('convergence', option, dtype=float)
        # sort refinement factors so we are always starting with coarsest
        refinement_factors = sorted(refinement_factors)[::-1]

        nres = len(refinement_factors)

        model = config.get('ocean', 'model')
        section = config['merry_go_round']

        use_mplstyle()
        fig, axes = plt.subplots(
            nrows=nres,
            ncols=3,
            figsize=(12, 2 * nres),
            constrained_layout=True,
            sharex=True,
            sharey=True,
        )

        section = config['convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_hour = 3600.0
        time = eval_time * s_per_hour

        for i, refinement_factor in enumerate(refinement_factors):
            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=self.refinement
            )
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=self.refinement
            )

            ds_mesh = self.open_model_dataset(
                f'mesh_r{refinement_factor:02g}.nc'
            )
            ds_init = self.open_model_dataset(
                f'init_r{refinement_factor:02g}.nc'
            )
            ds = self.open_model_dataset(
                f'output_r{refinement_factor:02g}.nc', decode_times=False
            )

            nx = ds_mesh.sizes['nCells'] // 4

            zMid = ds.refZMid.values
            xCell = ds_mesh.xCell.values

            dz = zMid[0] - zMid[1]
            dx = xCell[1] - xCell[0]

            # lower left corner of quad cell
            z = np.insert(zMid - dz / 2.0, [0], zMid[0] - dz / 2)
            x = np.insert(xCell[0:nx] + dx / 2.0, 0, dx)
            # mesh the coordinate data
            X, Z = np.meshgrid(x, z)

            tracer_exact = ds_init.tracer1.isel(Time=0, nCells=slice(0, nx))

            if model == 'mpas-o':
                dt = time_since_start(ds.xtime.values)
            else:
                # time is seconds since the start of the simulation in Omega
                dt = ds.Time.values
            tidx = np.argmin(np.abs(dt - time))

            tracer_model = ds.tracer1.isel(Time=tidx, nCells=slice(0, nx))

            # Comparison plots
            tracer_error = tracer_model - tracer_exact

            # compute norm bounds using the coarsest simulation
            if i == 0:
                data_min = np.min(np.abs(tracer_exact.values))
                data_max = np.max(np.abs(tracer_exact.values))
                error_range = np.max(np.abs(tracer_error.values))

                tracer_norm = mcolors.Normalize(vmin=data_min, vmax=data_max)
                error_norm = mcolors.Normalize(
                    vmin=-error_range, vmax=error_range
                )

            c0 = axes[i, 0].pcolormesh(
                X,
                Z,
                tracer_model.values.T,
                cmap='cmo.thermal',
                norm=tracer_norm,
            )
            c1 = axes[i, 1].pcolormesh(
                X,
                Z,
                tracer_exact.values.T,
                cmap='cmo.thermal',
                norm=tracer_norm,
            )
            c2 = axes[i, 2].pcolormesh(
                X, Z, tracer_error.values.T, cmap='cmo.curl', norm=error_norm
            )

            axes[i, 0].annotate(
                (
                    f'$\\Delta z$={dz:g}m\n'
                    f'$\\Delta x$={resolution * 1e3:g}m \n'
                    f'$\\Delta t$={timestep}s'
                ),
                xy=(0, 0.5),
                xytext=(-axes[i, 0].yaxis.labelpad - 5, 0),
                xycoords=axes[i, 0].yaxis.label,
                textcoords='offset points',
                size='large',
                ha='right',
                va='center',
            )

        fig.colorbar(
            c0, label='Numerical solution', ax=axes[:, 0], location='top'
        )
        fig.colorbar(
            c1, label='Analytical solution', ax=axes[:, 1], location='top'
        )
        fig.colorbar(
            c2,
            label='Error (Numerical - Analytical)',
            ax=axes[:, 2],
            location='top',
        )

        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)
