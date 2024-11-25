from math import ceil

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D

from polaris import Step
from polaris.mpas import time_index_from_xtime
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.viz import use_mplstyle


class MixingAnalysis(Step):
    """
    A step for analyzing the output from sphere transport test cases

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW
        meshes

    case_name : str
        The name of the test case
    """
    def __init__(self, component, refinement_factors, icosahedral, subdir,
                 case_name, dependencies, refinement='both'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        subdir : str
            The subdirectory that the step resides in

        case_name: str
            The name of the test case

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        super().__init__(component=component, name='mixing_analysis',
                         subdir=subdir)
        self.refinement_factors = refinement_factors
        self.refinement = refinement
        self.case_name = case_name

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
        self.add_output_file('triplots.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        resolutions = list()
        for refinement_factor in self.refinement_factors:
            resolution = get_resolution_for_task(
                self.config, refinement_factor, self.refinement)
            resolutions.append(resolution)
        config = self.config
        section = config[self.case_name]
        eval_time = section.getfloat('mixing_evaluation_time')
        s_per_day = 86400.0
        zidx = 1
        nrows = int(ceil(len(resolutions) / 2))
        use_mplstyle()
        fig, axes = plt.subplots(nrows=nrows, ncols=2, sharex=True,
                                 sharey=True, figsize=(5.5, 7))
        for i, refinement_factor in enumerate(self.refinement_factors):
            ax = axes[int(i / 2), i % 2]
            _init_triplot_axes(ax)
            mesh_name = resolution_to_subdir(resolutions[i])
            ax.set(title=mesh_name)
            ds = xr.open_dataset(f'output_r{refinement_factor:02g}.nc')
            if i % 2 == 0:
                ax.set_ylabel("tracer3")
            if int(i / 2) == nrows - 1:
                ax.set_xlabel("tracer2")
            tidx = time_index_from_xtime(ds.xtime.values,
                                         eval_time * s_per_day)
            ds = ds.isel(Time=tidx)
            ds = ds.isel(nVertLevels=zidx)
            tracer2 = ds["tracer2"].values
            tracer3 = ds["tracer3"].values
            ax.plot(tracer2, tracer3, '.', markersize=1)
            ax.set_aspect('equal')
        if i % 2 < 1:
            ax = axes[int(i / 2), 1]
            ax.set_axis_off()
        plt.subplots_adjust(wspace=0.1, hspace=0.1)
        fig.suptitle('Correlated tracers 2-d')
        fig.savefig('triplots.png', bbox_inches='tight')


def _init_triplot_axes(ax):
    lw = 0.4
    topline = Line2D([0.1, 1.0], [0.9, 0.9], color='k',
                     linestyle='-', linewidth=lw)
    midline = Line2D([0.1, 1.0], [0.9, 0.1], color='k',
                     linestyle='-', linewidth=lw)
    rightline = Line2D([1, 1], [0.1, 0.9], color='k',
                       linestyle='-', linewidth=lw)
    leftline = Line2D([0.1, 0.1], [0.1, 0.9], color='k',
                      linestyle='-', linewidth=lw)
    botline = Line2D([0.1, 1.0], [0.1, 0.1], color='k',
                     linestyle='-', linewidth=lw)
    crvx = np.linspace(0.1, 1)
    crvy = -0.8 * np.square(crvx) + 0.9
    ticks = np.array(range(6)) / 5
    ax.plot(crvx, crvy, 'k-', linewidth=1.25 * lw)
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.add_artist(topline)
    ax.add_artist(midline)
    ax.add_artist(botline)
    ax.add_artist(rightline)
    ax.add_artist(leftline)
    ax.set_xlim([0, 1.1])
    ax.set_ylim([0, 1.0])
    ax.text(0.98, 0.87, 'Range-preserving\n unmixing', fontsize=8,
            horizontalalignment='right', verticalalignment='top')
    ax.text(0.12, 0.12, 'Range-preserving\n unmixing', fontsize=8,
            horizontalalignment='left', verticalalignment='bottom')
    ax.text(0.5, 0.27, 'Real mixing', rotation=-40., fontsize=8)
    ax.text(0.02, 0.1, 'Overshooting', rotation=90., fontsize=8)
    ax.grid(color='lightgray')
