from polaris.config import PolarisConfigParser
from polaris.ocean.tests.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tests.baroclinic_channel.forward import Forward
from polaris.ocean.tests.baroclinic_channel.rpe_test.analysis import Analysis
from polaris.validate import compare_variables


class RpeTest(BaroclinicChannelTestCase):
    """
    The reference potential energy (RPE) test case for the baroclinic channel
    test group performs a 20-day integration of the model forward in time at
    5 different values of the viscosity at the given resolution.
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.baroclinic_channel.BaroclinicChannel
            The test group that this test case belongs to

        resolution : float
            The resolution of the test case in km
        """
        super().__init__(test_group=test_group, resolution=resolution,
                         name='rpe_test')

        self._add_steps()

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        super().configure()
        self._add_steps(config=self.config)

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()

        config = self.config
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']

        nus = config.getlist('baroclinic_channel', 'viscosities', dtype=float)
        for index, nu in enumerate(nus):
            name = f'rpe_test_{index + 1}_nu_{int(nu)}'
            compare_variables(test_case=self, variables=variables,
                              filename1=f'{name}/output.nc')

    def _add_steps(self, config=None):
        """ Add the steps in the test case either at init or set-up """

        if config is None:
            # get just the default config options for baroclinic_channel so
            # we can get the default viscosities
            config = PolarisConfigParser()
            package = 'polaris.ocean.tests.baroclinic_channel'
            config.add_from_package(package, 'baroclinic_channel.cfg')

        for step in list(self.steps):
            if step.startswith('rpe_test') or step == 'analysis':
                # remove previous RPE forward or analysis steps
                self.steps.pop(step)

        resolution = self.resolution

        nus = config.getlist('baroclinic_channel', 'viscosities', dtype=float)
        for index, nu in enumerate(nus):
            name = f'rpe_test_{index + 1}_nu_{int(nu)}'
            step = Forward(
                test_case=self, name=name, subdir=name,
                ntasks=None, min_tasks=None, openmp_threads=1,
                resolution=resolution, nu=float(nu))

            step.add_yaml_file(
                'polaris.ocean.tests.baroclinic_channel.rpe_test',
                'forward.yaml')
            self.add_step(step)

        self.add_step(
            Analysis(test_case=self, resolution=resolution, nus=nus))
