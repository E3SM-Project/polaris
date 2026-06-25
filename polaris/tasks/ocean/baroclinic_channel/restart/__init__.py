from polaris import Task as Task
from polaris.tasks.ocean.baroclinic_channel.forward import (
    Forward as Forward,
)
from polaris.tasks.ocean.baroclinic_channel.validate import (
    Validate as Validate,
)


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
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.baroclinic_channel.init.Init
            A shared step for creating the initial state
        """
        super().__init__(component=component, name='restart', indir=indir)

        self.add_step(init, symlink='init')

        full = Forward(
            component=component,
            resolution=resolution,
            run_time_steps=2,
            name='full_run',
            indir=self.subdir,
        )
        self.add_step(full)

        restart = Forward(
            component=component,
            resolution=resolution,
            run_time_steps=1,
            start_time_steps=1,
            name='restart_run',
            indir=self.subdir,
        )
        restart.add_dependency(full, full.name)
        self.add_step(restart)

        self.add_step(
            Validate(
                component=component,
                step_subdirs=['full_run', 'restart_run'],
                indir=self.subdir,
            )
        )
