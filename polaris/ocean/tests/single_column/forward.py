from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of baroclinic
    channel test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km

    resources_fixed : bool
        Whether resources were set already and shouldn't be updated
        algorithmically

    dt : float
        The model time step in seconds

    btr_dt : float
        The model barotropic time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
        NOTE: not currently used
    """
    def __init__(self, test_case, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1, nu=None,
                 run_time_steps=None):
        """
        Create a new test case

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        resolution : km
            The resolution of the test case in km

        name : str
            the name of the test case

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use

        """
        super().__init__(test_case=test_case, name=name, subdir=subdir,
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='initial_state.nc',
                            target='../initial_state/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../initial_state/culled_graph.info')

        self.add_yaml_file('polaris.ocean.tests.single_column',
                           'forward.yaml')

        self.add_output_file(filename='output.nc')

        self.resources_fixed = (ntasks is not None)

        self.dt = None
        self.btr_dt = None
