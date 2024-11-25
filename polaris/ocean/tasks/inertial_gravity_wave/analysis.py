import xarray as xr

from polaris.ocean.convergence.analysis import ConvergenceAnalysis
from polaris.ocean.tasks.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)


class Analysis(ConvergenceAnalysis):
    """
    A step for analysing the output from the inertial gravity wave
    test case

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run
    """
    def __init__(self, component, subdir, dependencies, refinement='both'):
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
        """
        convergence_vars = [{'name': 'ssh',
                             'title': 'SSH',
                             'zidx': None}]
        super().__init__(component=component, subdir=subdir,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars,
                         refinement=refinement)

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
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
        init = xr.open_dataset(f'init_r{refinement_factor:02g}.nc')
        exact = ExactSolution(init, self.config)
        if field_name != 'ssh':
            raise ValueError(f'{field_name} is not currently supported')
        return exact.ssh(time)
