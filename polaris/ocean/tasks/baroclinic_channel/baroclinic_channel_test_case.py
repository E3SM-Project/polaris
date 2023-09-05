from polaris import Task
from polaris.ocean.tasks.baroclinic_channel.init import Init


class BaroclinicChannelTestCase(Task):
    """
    The superclass for all baroclinic channel test cases with shared
    functionality

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """

    def __init__(self, component, resolution, name, indir):
        """
        Create the test case, including adding the ``init`` step

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        name : str
            The name of the test case

        indir : str
            the directory the task is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name=name,
                         indir=indir)

        self.resolution = resolution
        self.add_step(
            Init(component=component, resolution=resolution,
                 indir=self.subdir))

    def configure(self):
        """
        Add the config file common to baroclinic channel tests
        """
        self.config.add_from_package('polaris.ocean.tasks.baroclinic_channel',
                                     'baroclinic_channel.cfg')
