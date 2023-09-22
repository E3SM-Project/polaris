from polaris import Task
from polaris.ocean.tasks.baroclinic_channel.restart.restart_step import (
    RestartStep,
)
from polaris.ocean.tasks.baroclinic_channel.validate import Validate


class Restart(Task):
    """
    A baroclinic channel restart test case, which makes sure the model
    produces identical results with one longer run and two shorter runs with a
    restart in between.
    """

    def __init__(self, component, resolution, indir, init):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.baroclinic_channel.init.Init
            A shared step for creating the initial state
        """
        super().__init__(component=component, name='restart', indir=indir)

        self.add_step(init, symlink='init')

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

    def configure(self):
        """
        Add the config file common to baroclinic channel tests
        """
        self.config.add_from_package('polaris.ocean.tasks.baroclinic_channel',
                                     'baroclinic_channel.cfg')
