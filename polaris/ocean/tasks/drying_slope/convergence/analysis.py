import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import interp1d

from polaris.ocean.convergence.analysis import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the convergence of drying slope results and producing
    a convergence plot.

    Attributes
    ----------
    damping_coeff : float
        The Rayleigh damping coefficient used for the forward runs
    """
    def __init__(self, component, subdir, dependencies,
                 damping_coeff):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

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
                         dependencies=dependencies,
                         convergence_vars=convergence_vars)

        # We won't use all of these files but we link them all just in case
        # the user changes convergence_eval_time
        for time in ['0.05', '0.15', '0.25', '0.30', '0.40', '0.50']:
            filename = f'r{damping_coeff}d{time}-' \
                       f'analytical.csv'
            self.add_input_file(filename=filename, target=filename,
                                database='drying_slope')

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

        # Get the MPAS cell locations
        init = xr.open_dataset(f'{mesh_name}_init.nc')
        y_min = init.yCell.min()
        x_offset = y_min.values / 1000.
        init = init.drop_vars(np.setdiff1d([j for j in init.variables],
                                           ['yCell', 'ssh']))

        init = init.isel(Time=0)
        x_mpas = init.yCell / 1000.0

        # Load the analytical solution
        # we need to convert time from seconds to days for filename
        day = time / (3600. * 24.)
        datafile = f'./r{self.damping_coeff}d{day:.2f}-'\
                   f'analytical.csv'
        data = pd.read_csv(datafile, header=None)
        x_exact = data[0] + x_offset
        ssh_exact = -data[1]

        # Set MPAS locations out of analytical bounds to nans
        x_min = np.min(x_exact)
        x_max = np.max(x_exact)
        x_mpas[x_mpas < x_min] = np.nan
        x_mpas[x_mpas > x_max] = np.nan

        # In the original version we interpolated mpas data to exact data
        # location
        # here we do the opposite because we don't want to have to get the
        # exact data locations from within the shared convergence step
        # we need to interpolate to the mpas mesh locations
        f = interp1d(x_exact, ssh_exact)
        ssh_exact_interp = f(x_mpas)

        return ssh_exact_interp
