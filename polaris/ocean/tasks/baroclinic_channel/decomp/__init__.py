from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.validate import Validate


class Decomp(BaroclinicChannelTestCase):
    """
    A baroclinic channel decomposition task, which makes sure the model
    produces identical results on 1 and 4 cores.
    """

    def __init__(self, component, resolution, indir):
        """
        Create the task

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the task in km

        indir : str
            the directory the task is in, to which ``name`` will be appended
        """

        super().__init__(component=component, resolution=resolution,
                         name='decomp', indir=indir)

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
