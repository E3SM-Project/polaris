import datetime
import warnings

import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.manufactured_solution.exact_solution import (
    ExactSolution,
)


class Analysis(Step):
    """
    A step for analysing the output from the manufactured solution
    test case

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run
    """
    def __init__(self, component, resolutions, taskdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        taskdir : str
            The subdirectory that the task belongs to
        """
        super().__init__(component=component, name='analysis', indir=taskdir)
        self.resolutions = resolutions

        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            self.add_input_file(
                filename=f'init_{mesh_name}.nc',
                target=f'../init/{mesh_name}/initial_state.nc')
            self.add_input_file(
                filename=f'output_{mesh_name}.nc',
                target=f'../forward/{mesh_name}/output.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        resolutions = self.resolutions

        section = config['manufactured_solution']
        conv_thresh = section.getfloat('conv_thresh')
        conv_max = section.getfloat('conv_max')

        rmse = []
        for i, res in enumerate(resolutions):
            mesh_name = f'{res:g}km'
            init = xr.open_dataset(f'init_{mesh_name}.nc')
            ds = xr.open_dataset(f'output_{mesh_name}.nc')
            exact = ExactSolution(config, init)

            t0 = datetime.datetime.strptime(ds.xtime.values[0].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            tf = datetime.datetime.strptime(ds.xtime.values[-1].decode(),
                                            '%Y-%m-%d_%H:%M:%S')
            t = (tf - t0).total_seconds()
            ssh_model = ds.ssh.values[-1, :]
            rmse.append(np.sqrt(np.mean((ssh_model - exact.ssh(t).values)**2)))

        p = np.polyfit(np.log10(resolutions), np.log10(rmse), 1)
        conv = p[0]

        if conv < conv_thresh:
            raise ValueError(f'order of convergence '
                             f' {conv} < min tolerence {conv_thresh}')

        if conv > conv_max:
            warnings.warn(f'order of convergence '
                          f'{conv} > max tolerence {conv_max}')
