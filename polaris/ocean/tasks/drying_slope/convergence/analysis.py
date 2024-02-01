import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import interp1d

from polaris.ocean.convergence import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the convergence of drying slope results and producing
    a convergence plot.

    Attributes
    ----------
    damping_coeff : float
        The Rayleigh damping coefficient used for the forward runs

    resolutions : float
        The resolution of the test case

    times : list of float
        The times at which to compare to the analytical solution
    """
    def __init__(self, component, resolutions, subdir, dependencies,
                 damping_coeff):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step

        damping_coeff: float
            the value of the rayleigh damping coefficient
        """
        self.damping_coeff = damping_coeff
        convergence_vars = [{'name': 'ssh',
                             'title': 'SSH',
                             'zidx': None}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars)

    def exact_solution(self, mesh_name, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the initial condition file

        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        time : float
            The time at which to evaluate the exact solution in seconds.
            For the default method, we always use the initial state.

        zidx : int, optional
            The z-index for the vertical level at which to evaluate the exact
            solution

        Returns
        -------
        solution : xarray.DataArray
            The exact solution as derived from the initial condition
        """
        if field_name != 'ssh':
            raise ValueError(f'{field_name} is not currently supported')
        # we need to convert time from seconds to days for filename
        day = time / (3600. * 24.)
        datafile = f'./r{self.damping_coeff}d{day:02g}-'\
                   f'analytical.csv'
        init = xr.open_dataset(f'{mesh_name}_init.nc')
        init = init.drop_vars(np.setdiff1d([j for j in init.variables],
                                           ['yCell', 'ssh']))
        init = init.isel(Time=0)

        data = pd.read_csv(datafile, header=None)
        x_exact = data[0]
        ssh_exact = -data[1]
        f = interp1d(x_exact, ssh_exact)
        x_mpas = init.yCell.values / 1000.0
        # we need to interpolate to the mpas mesh locations
        idx_min = np.argwhere(x_exact - x_mpas[0] >= 0.).item(0)
        idx_max = np.argwhere(x_exact - x_mpas[-1] <= 0.).item(-1)
        ssh_exact_interp = xr.full_like(x_mpas, fill_value=np.nan)
        ssh_exact_interp[idx_min:idx_max] = f(x_mpas[idx_min:idx_max])
        return ssh_exact_interp
