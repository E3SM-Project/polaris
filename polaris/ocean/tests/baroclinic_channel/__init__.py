from polaris import TestGroup
from polaris.ocean.tests.baroclinic_channel.baroclinic_channel_test_case import (  # noqa: E501
    BaroclinicChannelTestCase,
)
from polaris.ocean.tests.baroclinic_channel.decomp import Decomp
from polaris.ocean.tests.baroclinic_channel.default import Default
from polaris.ocean.tests.baroclinic_channel.restart import Restart
from polaris.ocean.tests.baroclinic_channel.rpe import Rpe
from polaris.ocean.tests.baroclinic_channel.threads import Threads


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
                Decomp(test_group=self, resolution=resolution))

            self.add_test_case(
                Restart(test_group=self, resolution=resolution))

            self.add_test_case(
                Threads(test_group=self, resolution=resolution))

        for resolution in [1., 4., 10.]:
            self.add_test_case(
                Rpe(test_group=self, resolution=resolution))
