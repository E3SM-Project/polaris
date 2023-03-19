from polaris.ocean.tests.baroclinic_channel.baroclinic_channel_test_case import (  # noqa: E501
    BaroclinicChannelTestCase,
)
from polaris.ocean.tests.baroclinic_channel.decomp_test import DecompTest
from polaris.ocean.tests.baroclinic_channel.default import Default
from polaris.ocean.tests.baroclinic_channel.restart_test import RestartTest
from polaris.testgroup import TestGroup


class BaroclinicChannel(TestGroup):
    """
    A test group for baroclinic channel test cases
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component,
                         name='baroclinic_channel')

        for resolution in [10.]:
            self.add_test_case(
                Default(test_group=self, resolution=resolution))

            self.add_test_case(
                DecompTest(test_group=self, resolution=resolution))

            self.add_test_case(
                RestartTest(test_group=self, resolution=resolution))
