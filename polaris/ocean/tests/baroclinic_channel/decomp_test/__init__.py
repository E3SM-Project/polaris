from polaris.ocean.tests.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tests.baroclinic_channel.forward import Forward
from polaris.validate import compare_variables


class DecompTest(BaroclinicChannelTestCase):
    """
    A decomposition test case for the baroclinic channel test group, which
    makes sure the model produces identical results on 1 and 4 cores.
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.baroclinic_channel.BaroclinicChannel
            The test group that this test case belongs to

        resolution : float
            The resolution of the test case in km
        """

        super().__init__(test_group=test_group, resolution=resolution,
                         name='decomp_test')

        for procs in [4, 8]:
            name = f'{procs}proc'

            self.add_step(Forward(
                test_case=self, name=name, subdir=name, ntasks=procs,
                min_tasks=procs, openmp_threads=1,
                resolution=resolution))

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``4proc`` and ``8proc`` steps with each other
        and with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(test_case=self, variables=variables,
                          filename1='4proc/output.nc',
                          filename2='8proc/output.nc')
