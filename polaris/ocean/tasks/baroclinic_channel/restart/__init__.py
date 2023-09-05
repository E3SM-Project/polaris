from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannelTestCase
from polaris.ocean.tasks.baroclinic_channel.restart.restart_step import (
    RestartStep,
)
from polaris.validate import compare_variables


class Restart(BaroclinicChannelTestCase):
    """
    A baroclinic channel restart test case, which makes sure the model
    produces identical results with one longer run and two shorter runs with a
    restart in between.
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
                         name='restart')

        full = RestartStep(task=self, resolution=resolution,
                           name='full_run')
        self.add_step(full)

        restart = RestartStep(task=self, resolution=resolution,
                              name='restart_run')
        restart.add_dependency(full, full.name)
        self.add_step(restart)

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``full_run`` and ``restart_run`` steps with
        each other and with a baseline if one was provided
        """
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='full_run/output.nc',
                          filename2='restart_run/output.nc')
