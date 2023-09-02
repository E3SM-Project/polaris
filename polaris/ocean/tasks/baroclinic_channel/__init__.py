from polaris import TestGroup
from polaris.ocean.tasks.baroclinic_channel.baroclinic_channel_test_case import (  # noqa: E501
    BaroclinicChannelTestCase,
)
from polaris.ocean.tasks.baroclinic_channel.decomp import Decomp
from polaris.ocean.tasks.baroclinic_channel.default import Default
from polaris.ocean.tasks.baroclinic_channel.restart import Restart
from polaris.ocean.tasks.baroclinic_channel.rpe import Rpe
from polaris.ocean.tasks.baroclinic_channel.threads import Threads


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
            self.add_task(
                Default(test_group=self, resolution=resolution))

            self.add_task(
                Decomp(test_group=self, resolution=resolution))

            self.add_task(
                Restart(test_group=self, resolution=resolution))

            self.add_task(
                Threads(test_group=self, resolution=resolution))

        for resolution in [1., 4., 10.]:
            self.add_task(
                Rpe(test_group=self, resolution=resolution))
