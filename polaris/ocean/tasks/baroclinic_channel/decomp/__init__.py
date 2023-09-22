from polaris import Task
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.validate import Validate


class Decomp(Task):
    """
    A baroclinic channel decomposition task, which makes sure the model
    produces identical results on 1 and 4 cores.
    """

    def __init__(self, component, resolution, indir, init):
        """
        Create the task

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the task in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.baroclinic_channel.init.Init
            A shared step for creating the initial state
        """

        super().__init__(component=component, name='decomp', indir=indir)

        self.add_step(init, symlink='init')

        subdirs = list()
        for procs in [4, 8]:
            name = f'{procs}proc'

            self.add_step(Forward(
                component=component, name=name, indir=self.subdir,
                ntasks=procs, min_tasks=procs, openmp_threads=1,
                resolution=resolution, run_time_steps=3))
            subdirs.append(name)
        self.add_step(Validate(component=component, step_subdirs=subdirs,
                               indir=self.subdir))

    def configure(self):
        """
        Add the config file common to baroclinic channel tests
        """
        self.config.add_from_package('polaris.ocean.tasks.baroclinic_channel',
                                     'baroclinic_channel.cfg')
