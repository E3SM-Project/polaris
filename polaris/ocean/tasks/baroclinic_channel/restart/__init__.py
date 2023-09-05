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

    def __init__(self, component, resolution, indir):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            the directory the task is in, to which ``name`` will be appended
        """
        super().__init__(component=component, resolution=resolution,
                         name='restart', indir=indir)

        full = RestartStep(component=component, resolution=resolution,
                           name='full_run', indir=self.subdir)
        self.add_step(full)

        restart = RestartStep(component=component, resolution=resolution,
                              name='restart_run', indir=self.subdir)
        restart.add_dependency(full, full.name)
        self.add_step(restart)

        self.add_step(Validate(component=component,
                               step_subdirs=['full_run', 'restart_run'],
                               indir=self.subdir))
