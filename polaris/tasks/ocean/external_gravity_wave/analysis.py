from polaris.ocean.convergence.analysis import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the external gravity wave test case
    """

    def __init__(self, component, subdir, dependencies, refinement='both'):
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

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        convergence_vars = [{'name': 'tracer1', 'title': 'tracer1', 'zidx': 0}]
        super().__init__(
            component=component,
            subdir=subdir,
            dependencies=dependencies,
            convergence_vars=convergence_vars,
            refinement=refinement,
        )

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        refinement_factor : float
            The factor by which to scale space, time or both

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
            The exact solution with dimension nCells
        """

        if field_name != 'tracer1':
            print(
                f'Variable {field_name} not available as an analytic '
                'solution for the cosine_bell test case'
            )

        return
