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

    def __init__(self, test_group, resolution, name):
        """
        Create the test case, including adding the ``init`` step

        Parameters
        ----------
        test_group : polaris.ocean.tasks.baroclinic_channel.BaroclinicChannel
            The test group that this test case belongs to

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
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        self.add_step(
            Init(task=self, resolution=resolution))

    def validate(self):
        """
        Compare ``temperature``, ``salinity`` and ``layerThickness`` from the
        initial condition with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')
