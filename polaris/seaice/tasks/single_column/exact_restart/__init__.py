import os

from polaris import Task
from polaris.seaice.tasks.single_column.forward import Forward
from polaris.validate import compare_variables


class ExactRestart(Task):
    """
    A restart test case for the single column test group, which makes sure
    the model produces identical results with one longer run and two shorter
    runs with a restart in between.

    Attributes
    ----------

    """

    def __init__(self, test_group):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.seaice.tasks.single_column.SingleColumn
            The test group that this test case belongs to

        """
        name = 'exact_restart'
        super().__init__(test_group=test_group, name=name)

        step = Forward(task=self, name='full_run')
        step.add_output_file(
            filename='restarts/restart.2000-01-01_12.00.00.nc')
        step.add_output_file(
            filename='restarts/restart.2000-01-02_00.00.00.nc')

        step.add_namelist_file(
            package='polaris.seaice.tasks.single_column.exact_restart',
            namelist='namelist.full')
        step.add_streams_file(
            package='polaris.seaice.tasks.single_column.exact_restart',
            streams='streams.full')
        self.add_step(step)

        step = Forward(task=self, name='restart_run')
        step.add_input_file(
            filename='restarts/restart.2000-01-01_12.00.00.nc',
            target='../../full_run/restarts/restart.2000-01-01_12.00.00.nc')

        step.add_output_file(
            filename='restarts/restart.2000-01-02_00.00.00.nc')

        step.add_namelist_file(
            package='polaris.seaice.tasks.single_column.exact_restart',
            namelist='namelist.restart')
        step.add_streams_file(
            package='polaris.seaice.tasks.single_column.exact_restart',
            streams='streams.restart')
        self.add_step(step)

    def validate(self):
        """
        Compare variables in the restart files at the end of each run.
        """
        super().validate()

        variables = ['iceAreaCategory',
                     'iceVolumeCategory',
                     'snowVolumeCategory',
                     'surfaceTemperature',
                     'iceEnthalpy',
                     'iceSalinity',
                     'snowEnthalpy',
                     'iceAge',
                     'firstYearIceArea',
                     'levelIceArea',
                     'levelIceVolume',
                     'pondArea',
                     'pondDepth',
                     'pondLidThickness',
                     'uVelocity',
                     'vVelocity',
                     'freezeOnset',
                     'snowfallRate',
                     'pondSnowDepthDifference',
                     'pondLidMeltFluxFraction',
                     'solarZenithAngleCosine',
                     'shortwaveScalingFactor',
                     'shortwaveVisibleDirectDown',
                     'shortwaveVisibleDiffuseDown',
                     'shortwaveIRDirectDown',
                     'shortwaveIRDiffuseDown',
                     'oceanStressCellU',
                     'oceanStressCellV',
                     'seaSurfaceTemperature',
                     'freezingMeltingPotential',
                     'airOceanDragCoefficientRatio']
        compare_variables(task=self, variables=variables,
                          filename1='full_run/restarts/restart.2000-01-02_00.00.00.nc',  # noqa: E501
                          filename2='restart_run/restarts/restart.2000-01-02_00.00.00.nc')  # noqa: E501
