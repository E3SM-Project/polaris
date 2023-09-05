from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.viz import Viz


class Default(BaroclinicChannelTestCase):
    """
    The default baroclinic channel test case simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.
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
                         name='default', indir=indir)

        self.add_step(
            Forward(component=component, indir=self.subdir, ntasks=4,
                    min_tasks=4, openmp_threads=1, resolution=resolution,
                    run_time_steps=3))

        self.add_step(
            Viz(component=component, indir=self.subdir))
