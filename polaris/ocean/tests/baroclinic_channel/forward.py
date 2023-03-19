import time

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
    """
    def __init__(self, test_case, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1, nu=None):
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

        nu : float, optional
            the viscosity (if different from the default for the test group)
        """
        self.resolution = resolution
        super().__init__(test_case=test_case, name=name, subdir=subdir,
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)
        self.add_yaml_file('polaris.ocean.tests.baroclinic_channel',
                           'forward.yaml')

        if nu is not None:
            # update the viscosity to the requested value
            self.add_model_config_options(options=dict(config_mom_del2=nu))

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='init.nc',
                            target='../initial_state/ocean.nc')
        self.add_input_file(filename='graph.info',
                            target='../initial_state/culled_graph.info')

        self.add_output_file(filename='output.nc')

        self.resources_fixed = (ntasks is not None)

    def setup(self):
        """
        Set namelist options base on config options
        """
        options = self.get_dt_model_options()
        self.add_model_config_options(options=options)
        self.resources_fixed = (self.ntasks is not None)
        if not self.resources_fixed:
            # we do this once at setup with the default config options
            self._get_resources()
        super().setup()

    def constrain_resources(self, available_cores):
        """
        Update resources at runtime from config options
        """
        if not self.resources_fixed:
            # we do this again at runtime in case config options have changed
            self._get_resources()
        super().constrain_resources(available_cores)

    def runtime_setup(self):
        """
        Update the resources and time step in case the user has update config
        options
        """
        super().runtime_setup()

        # update dt in case the user has changed dt_per_km
        options = self.get_dt_model_options()
        self.update_model_config_at_runtime(options=options)

    def get_dt_model_options(self):
        """
        Get the time steps for the given resolution

        Returns
        -------
        options : dict
            model config options related to time steps to replace
        """
        config = self.config

        options = dict()
        for opt in ['dt', 'btr_dt']:
            # dt is proportional to resolution: default 30 seconds per km
            dt_per_km = config.getfloat('baroclinic_channel', f'{opt}_per_km')
            dt = dt_per_km * self.resolution
            # https://stackoverflow.com/a/1384565/7728169
            options[f'config_{opt}'] = \
                time.strftime('%H:%M:%S', time.gmtime(dt))

        return options

    def _get_resources(self):
        section = self.config['baroclinic_channel']
        nx = section.getint('nx')
        ny = section.getint('ny')
        goal_cells_per_core = section.getfloat('goal_cells_per_core')
        max_cells_per_core = section.getfloat('max_cells_per_core')

        # ideally, about 200 cells per core
        self.ntasks = max(1, round(nx * ny / goal_cells_per_core + 0.5))
        # In a pinch, about 2000 cells per core
        self.min_tasks = max(1, round(nx * ny / max_cells_per_core + 0.5))
