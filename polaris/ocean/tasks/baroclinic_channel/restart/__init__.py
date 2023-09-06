from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.restart.restart_step import (
    RestartStep,
)
from polaris.ocean.tasks.baroclinic_channel.validate import Validate


class Restart(BaroclinicChannelTestCase):
    """
    A baroclinic channel restart test case, which makes sure the model
    produces identical results with one longer run and two shorter runs with a
    restart in between.
    """

    def __init__(self, component, resolution):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km
        """
        super().__init__(component=component, resolution=resolution,
                         name='restart')

        full = RestartStep(task=self, resolution=resolution,
                           name='full_run')
        self.add_step(full)

        restart = RestartStep(task=self, resolution=resolution,
                              name='restart_run')
        restart.add_dependency(full, full.name)
        self.add_step(restart)

        self.add_step(Validate(task=self,
                               step_subdirs=['full_run', 'restart_run']))
