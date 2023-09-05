from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.validate import compare_variables


class Threads(BaroclinicChannelTestCase):
    """
    A thread test case for the baroclinic channel test group, which makes sure
    the model produces identical results with 1 and 2 threads.
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tasks.baroclinic_channel.BaroclinicChannel
            The test group that this test case belongs to

        resolution : float
            The resolution of the test case in km
        """

        super().__init__(test_group=test_group, resolution=resolution,
                         name='threads')

        for openmp_threads in [1, 2]:
            name = f'{openmp_threads}thread'
            self.add_step(Forward(
                task=self, name=name, subdir=name, ntasks=4,
                min_tasks=4, openmp_threads=openmp_threads,
                resolution=resolution, run_time_steps=3))

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``1thread`` and ``2thread`` steps with each
        other and with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='1thread/output.nc',
                          filename2='2thread/output.nc')
