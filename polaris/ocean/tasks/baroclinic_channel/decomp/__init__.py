from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.validate import compare_variables


class Decomp(BaroclinicChannelTestCase):
    """
    A baroclinic channel decomposition task, which makes sure the model
    produces identical results on 1 and 4 cores.
    """

    def __init__(self, component, resolution):
        """
        Create the task

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the task in km
        """

        super().__init__(component=component, resolution=resolution,
                         name='decomp')

        for procs in [4, 8]:
            name = f'{procs}proc'

            self.add_step(Forward(
                task=self, name=name, subdir=name, ntasks=procs,
                min_tasks=procs, openmp_threads=1,
                resolution=resolution, run_time_steps=3))

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``4proc`` and ``8proc`` steps with each other
        and with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='4proc/output.nc',
                          filename2='8proc/output.nc')
