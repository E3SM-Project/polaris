import datetime
from math import ceil

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir


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
    def __init__(self, component, resolutions, icosahedral, subdir,
                 case_name, dependencies):
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
        self.resolutions = resolutions
        self.case_name = case_name

        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            base_mesh = dependencies['mesh'][resolution]
            init = dependencies['init'][resolution]
            forward = dependencies['forward'][resolution]
            self.add_input_file(
                filename=f'{mesh_name}_mesh.nc',
                work_dir_target=f'{base_mesh.path}/base_mesh.nc')
            self.add_input_file(
                filename=f'{mesh_name}_init.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'{mesh_name}_output.nc',
                work_dir_target=f'{forward.path}/output.nc')
        self.add_output_file('triplots.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        resolutions = self.resolutions
        config = self.config
        section = config[self.case_name]
        eval_time = section.getfloat('mixing_evaluation_time')
        s_per_day = 86400.0
        zidx = 1
        nrows = int(ceil(len(resolutions) / 2))
        fig, axes = plt.subplots(nrows=nrows, ncols=2, sharex=True,
                                 sharey=True, figsize=(5.5, 7))
        plt.subplots_adjust(wspace=0.1)
        for i, resolution in enumerate(resolutions):
            ax = axes[int(i / 2), i % 2]
            _init_triplot_axes(ax)
            mesh_name = resolution_to_subdir(resolution)
            ax.set(title=mesh_name)
            ds = xr.open_dataset(f'{mesh_name}_output.nc')
            if i % 2 == 0:
                ax.set_ylabel("tracer3")
            if int(i / 2) == 2:
                ax.set_xlabel("tracer2")
            tidx = _time_index_from_xtime(ds.xtime.values,
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
        fig.suptitle('Correlated tracers 2-d')
        fig.savefig('triplots.png', bbox_inches='tight')


def _init_triplot_axes(ax):
    lw = 0.4
    topline = Line2D([0.1, 1.0], [0.9, 0.9], color='k',
                     linestyle='-', linewidth=lw)
    botline = Line2D([0.1, 1.0], [0.9, 0.1], color='k',
                     linestyle='-', linewidth=lw)
    rightline = Line2D([1, 1], [0.1, 0.9], color='k',
                       linestyle='-', linewidth=lw)
    leftline = Line2D([0.1, 0.1], [0.1, 0.9], color='k',
                      linestyle='-', linewidth=lw)
    crvx = np.linspace(0.1, 1)
    crvy = -0.8 * np.square(crvx) + 0.9
    ticks = np.array(range(6)) / 5
    ax.plot(crvx, crvy, 'k-', linewidth=1.25 * lw)
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.add_artist(topline)
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
    ax.text(0.05, 0.05, 'Overshooting', rotation=-90., fontsize=8)
    ax.grid(color='lightgray')


def _time_index_from_xtime(xtime, dt_target):
    """
    Determine the time index at which to evaluate convergence

    Parameters
    ----------
    xtime: list of str
        Times in the dataset
    dt_target: float
        Time in seconds at which to evaluate convergence

    Returns
    -------
    tidx: int
        Index in xtime that is closest to dt_target
    """
    t0 = datetime.datetime.strptime(xtime[0].decode(),
                                    '%Y-%m-%d_%H:%M:%S')
    dt = np.zeros((len(xtime)))
    for idx, xt in enumerate(xtime):
        t = datetime.datetime.strptime(xt.decode(),
                                       '%Y-%m-%d_%H:%M:%S')
        dt[idx] = (t - t0).total_seconds()
    return np.argmin(np.abs(np.subtract(dt, dt_target)))
