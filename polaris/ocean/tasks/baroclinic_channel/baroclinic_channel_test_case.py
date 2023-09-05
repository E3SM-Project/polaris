import os

from polaris import Task
from polaris.ocean.tasks.baroclinic_channel.init import Init
from polaris.validate import compare_variables


class BaroclinicChannelTestCase(Task):
    """
    The superclass for all baroclinic channel test cases with shared
    functionality

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """

    def __init__(self, component, resolution, name):
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
        """
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join('baroclinic_channel', res_str, name)
        super().__init__(component=component, name=name,
                         subdir=subdir)

        self.add_step(
            Init(task=self, resolution=resolution))

    def configure(self):
        """
        Add the config file common to baroclinic channel tests
        """
        self.config.add_from_package('polaris.ocean.tasks.baroclinic_channel',
                                     'baroclinic_channel.cfg')

    def validate(self):
        """
        Compare ``temperature``, ``salinity`` and ``layerThickness`` from the
        initial condition with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')
