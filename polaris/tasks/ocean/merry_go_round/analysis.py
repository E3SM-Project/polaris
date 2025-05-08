from polaris.ocean.convergence.analysis import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from merry-go-round test case

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    case_name : str
        The name of the test case
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
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        convergence_vars = [
            {'name': 'tracer1', 'title': 'tracer1', 'zidx': 0},
            {'name': 'tracer2', 'title': 'tracer2', 'zidx': 0},
            {'name': 'tracer3', 'title': 'tracer3', 'zidx': 0},
        ]
        super().__init__(
            component=component,
            subdir=subdir,
            dependencies=dependencies,
            convergence_vars=convergence_vars,
            refinement=refinement,
        )
        # Note: there is no need to overwrite the default method exact_solution
        # which uses the initial condition
