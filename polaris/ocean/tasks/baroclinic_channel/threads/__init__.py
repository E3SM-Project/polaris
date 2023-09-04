from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.validate import Validate


class Threads(BaroclinicChannelTestCase):
    """
    A baroclinic channel thread test case, which makes sure the model produces
    identical results with 1 and 2 threads.
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
                         name='threads')

        subdirs = list()
        for openmp_threads in [1, 2]:
            name = f'{openmp_threads}thread'
            self.add_step(Forward(
                task=self, name=name, subdir=name, ntasks=4,
                min_tasks=4, openmp_threads=openmp_threads,
                resolution=resolution, run_time_steps=3))
            subdirs.append(name)
        self.add_step(Validate(task=self, step_subdirs=subdirs))
