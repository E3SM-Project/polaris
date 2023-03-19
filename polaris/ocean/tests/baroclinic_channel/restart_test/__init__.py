from polaris.ocean.tests.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tests.baroclinic_channel.forward import Forward
from polaris.validate import compare_variables


class RestartTest(BaroclinicChannelTestCase):
    """
    A restart test case for the baroclinic channel test group, which makes sure
    the model produces identical results with one longer run and two shorter
    runs with a restart in between.
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
                         name='restart_test')

        for part in ['full', 'restart']:
            name = f'{part}_run'
            step = Forward(test_case=self, name=name, subdir=name, ntasks=4,
                           min_tasks=4, openmp_threads=1,
                           resolution=resolution)
            package = 'polaris.ocean.tests.baroclinic_channel.restart_test'
            step.add_yaml_file(package=package,
                               yaml=f'{part}.yaml')
            self.add_step(step)

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``full_run`` and ``restart_run`` steps with
        each other and with a baseline if one was provided
        """
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(test_case=self, variables=variables,
                          filename1='full_run/output.nc',
                          filename2='restart_run/output.nc')
