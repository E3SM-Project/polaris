import datetime

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.ocean.tasks.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)
from polaris.viz import plot_horiz_field, use_mplstyle


class Viz(Step):
    """
    A step for visualizing the output from the inertial gravity wave
    test case

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

    refinement : str, optional
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time
    """
    def __init__(self, component, taskdir, dependencies, refinement='both'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        taskdir : str
            The subdirectory that the task belongs to

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
        refinement_factors = config.getlist('convergence', option,
                                            dtype=float)
        for refinement_factor in refinement_factors:
            base_mesh = dependencies['mesh'][refinement_factor]
            init = dependencies['init'][refinement_factor]
            forward = dependencies['forward'][refinement_factor]
            self.add_input_file(
                filename=f'mesh_r{refinement_factor:02g}.nc',
                work_dir_target=f'{base_mesh.path}/base_mesh.nc')
            self.add_input_file(
                filename=f'init_r{refinement_factor:02g}.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'output_r{refinement_factor:02g}.nc',
                work_dir_target=f'{forward.path}/output.nc')

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
        refinement_factors = config.getlist('convergence', option,
                                            dtype=float)
        nres = len(refinement_factors)

        section = config['inertial_gravity_wave']
        eta0 = section.getfloat('ssh_amplitude')

        use_mplstyle()
        fig, axes = plt.subplots(nrows=nres, ncols=3, figsize=(12, 2 * nres))
        rmse = []
        error_range = None
        for i, refinement_factor in enumerate(refinement_factors):
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=self.refinement)
            ds_mesh = xr.open_dataset(f'mesh_r{refinement_factor:02g}.nc')
            ds_init = xr.open_dataset(f'init_r{refinement_factor:02g}.nc')
            ds = xr.open_dataset(f'output_r{refinement_factor:02g}.nc')
            exact = ExactSolution(ds_init, config)

            t0 = datetime.datetime.strptime(ds.xtime.values[0].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            tf = datetime.datetime.strptime(ds.xtime.values[-1].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            t = (tf - t0).total_seconds()
            ssh_model = ds.ssh.values[-1, :]
            rmse.append(np.sqrt(np.mean((ssh_model - exact.ssh(t).values)**2)))

            # Comparison plots
            ds['ssh_exact'] = exact.ssh(t)
            ds['ssh_error'] = ssh_model - exact.ssh(t)
            if error_range is None:
                error_range = np.max(np.abs(ds.ssh_error.values))

            cell_mask = ds_init.maxLevelCell >= 1
            patches, patch_mask = plot_horiz_field(
                ds, ds_mesh, 'ssh', ax=axes[i, 0], cmap='cmo.balance',
                t_index=ds.sizes["Time"] - 1, vmin=-eta0, vmax=eta0,
                cmap_title="SSH (m)", cell_mask=cell_mask)
            plot_horiz_field(ds, ds_mesh, 'ssh_exact', ax=axes[i, 1],
                             cmap='cmo.balance',
                             vmin=-eta0, vmax=eta0, cmap_title="SSH (m)",
                             patches=patches, patch_mask=patch_mask)
            plot_horiz_field(ds, ds_mesh, 'ssh_error', ax=axes[i, 2],
                             cmap='cmo.balance',
                             cmap_title=r"$\Delta$ SSH (m)",
                             vmin=-error_range, vmax=error_range,
                             patches=patches, patch_mask=patch_mask)

        axes[0, 0].set_title('Numerical solution')
        axes[0, 1].set_title('Analytical solution')
        axes[0, 2].set_title('Error (Numerical - Analytical)')

        pad = 5
        for ax, refinement_factor in zip(axes[:, 0], refinement_factors):
            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=self.refinement)
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=self.refinement)

            ax.annotate(f'{resolution}km\n{timestep}s', xy=(0, 0.5),
                        xytext=(-ax.yaxis.labelpad - pad, 0),
                        xycoords=ax.yaxis.label, textcoords='offset points',
                        size='large', ha='right', va='center')

        fig.savefig('comparison.png', bbox_inches='tight', pad_inches=0.1)
