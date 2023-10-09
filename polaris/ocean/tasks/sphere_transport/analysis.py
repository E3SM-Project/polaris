from polaris.ocean.convergence import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from sphere transport test cases

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    case_name : str
        The name of the test case
    """
    def __init__(self, component, resolutions, subdir, case_name,
                 dependencies):
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

        case_name: str
            The name of the test case

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        self.case_name = case_name
        convergence_vars = [{'name': 'tracer1',
                             'title': 'tracer1',
                             'zidx': 1},
                            {'name': 'tracer2',
                             'title': 'tracer2',
                             'zidx': 1},
                            {'name': 'tracer3',
                             'title': 'tracer3',
                             'zidx': 1}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars)
        # Note: there is no need to overwrite the default method exact_solution
        # which uses the initial condition

    def convergence_parameters(self, field_name=None):
        """
        Get convergence parameters

        Parameters
        ----------
        field_name : str
            The name of the variable of which we evaluate convergence
            For cosine_bell, we use the same convergence rate for all fields
        Returns
        -------
        conv_thresh: float
            The minimum convergence rate

        conv_thresh: float
            The maximum convergence rate
        """
        config = self.config
        section = config[self.case_name]
        conv_thresh = section.getfloat(f'convergence_thresh_{field_name}')

        section = config['convergence']
        error_type = section.get('error_type')

        return conv_thresh, error_type
