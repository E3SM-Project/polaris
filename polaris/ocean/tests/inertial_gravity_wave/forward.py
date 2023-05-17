from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of "yet another
    channel" test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, test_case, resolution,
                 ntasks=None, min_tasks=None, openmp_threads=1):
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
        self.resolution = resolution
        super().__init__(test_case=test_case,
                         name=f'forward_{resolution}km',
                         subdir=f'{resolution}km/forward',
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        self.add_input_file(filename='initial_state.nc',
                            target='../initial_state/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../initial_state/culled_graph.info')

        self.add_output_file(filename='output.nc')

        self.add_yaml_file('polaris.ocean.config',
                           'single_layer.yaml')
        self.add_yaml_file('polaris.ocean.tests.inertial_gravity_wave',
                           'forward.yaml')

        dt_dict = {200: '00:10:00',
                   100: '00:05:00',
                   50: '00:02:30'}
        options = {'time_integration': {'config_dt': dt_dict[resolution]}}
        self.add_model_config_options(options)
