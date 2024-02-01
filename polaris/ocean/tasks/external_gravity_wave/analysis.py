from polaris.ocean.convergence import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the cosine bell test case
    """
    def __init__(self, component, resolutions, subdir, dependencies, dts):
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
        convergence_vars = [{'name': 'normalVelocity',
                             'title': 'normal velocity',
                             'zidx': 0},
                            {'name': 'layerThickness',
                             'title': 'layer thickness',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars, dts=dts)
