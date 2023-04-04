from polaris.ocean.tests.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tests.baroclinic_channel.restart_test.restart_step import (
    RestartStep,
)
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

        for name in ['full_run', 'restart_run']:
            self.add_step(
                RestartStep(test_case=self, resolution=resolution,
                            name=name))

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
