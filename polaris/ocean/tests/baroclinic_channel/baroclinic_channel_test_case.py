import os

import numpy as np

from polaris.ocean.tests.baroclinic_channel.initial_state import InitialState
from polaris.testcase import TestCase
from polaris.validate import compare_variables


class BaroclinicChannelTestCase(TestCase):
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
        Create the test case, including adding the ``initial_state`` step

        Parameters
        ----------
        test_group : polaris.ocean.tests.baroclinic_channel.BaroclinicChannel
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
            InitialState(test_case=self, resolution=resolution))

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        resolution = self.resolution
        config = self.config

        lx = config.getfloat('baroclinic_channel', 'lx')
        ly = config.getfloat('baroclinic_channel', 'ly')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        #
        # ny is required to be even for periodicity, and we do the same for nx
        # for consistency
        nx = max(2 * int(0.5 * lx / resolution + 0.5), 4)
        # factor of 2/sqrt(3) because of hexagonal mesh
        ny = max(2 * int(0.5 * ly * (2. / np.sqrt(3)) / resolution + 0.5), 4)
        dc = 1e3 * resolution

        config.set('baroclinic_channel', 'nx', f'{nx}')
        config.set('baroclinic_channel', 'ny', f'{ny}')
        config.set('baroclinic_channel', 'dc', f'{dc}')

    def validate(self):
        """
        Compare ``temperature``, ``salinity`` and ``layerThickness`` from the
        initial condition with a baseline if one was provided
        """
        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(test_case=self, variables=variables,
                          filename1='initial_state/initial_state.nc')
