from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.viz import Viz
from polaris.validate import compare_variables


class Default(BaroclinicChannelTestCase):
    """
    The default test case for the baroclinic channel test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
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
                         name='default')

        self.add_step(
            Forward(task=self, ntasks=4, min_tasks=4, openmp_threads=1,
                    resolution=resolution, run_time_steps=3))

        self.add_step(
            Viz(task=self))

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='forward/output.nc')
