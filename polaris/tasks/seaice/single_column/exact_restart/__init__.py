import os as os

from polaris import Task as Task
from polaris.tasks.seaice.single_column.exact_restart.validate import (
    Validate as Validate,
)
from polaris.tasks.seaice.single_column.forward import Forward as Forward


class ExactRestart(Task):
    """
    A single-column restart test case, which makes sure  the model produces
    identical results with one longer run and two shorter runs with a restart
    in between.
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.seaice.Seaice
            the component that that the task belongs to
        """
        name = 'exact_restart'
        subdir = os.path.join('single_column', name)
        super().__init__(component=component, name=name, subdir=subdir)

        validate_vars = [
            'iceAreaCategory',
            'iceVolumeCategory',
            'snowVolumeCategory',
            'surfaceTemperature',
            'iceEnthalpy',
            'iceSalinity',
            'snowEnthalpy',
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
            'airOceanDragCoefficientRatio',
        ]

        step = Forward(component=component, name='full_run', indir=self.subdir)
        step.add_output_file(
            filename='restarts/restart.2000-01-01_12.00.00.nc',
            validate_vars=validate_vars,
        )
        step.add_output_file(
            filename='restarts/restart.2000-01-02_00.00.00.nc',
            validate_vars=validate_vars,
        )

        step.add_namelist_file(
            package='polaris.tasks.seaice.single_column.exact_restart',
            namelist='namelist.full',
        )
        step.add_streams_file(
            package='polaris.tasks.seaice.single_column.exact_restart',
            streams='streams.full',
        )
        self.add_step(step)

        step = Forward(
            component=component, name='restart_run', indir=self.subdir
        )
        step.add_input_file(
            filename='restarts/restart.2000-01-01_12.00.00.nc',
            target='../../full_run/restarts/restart.2000-01-01_12.00.00.nc',
        )

        step.add_output_file(
            filename='restarts/restart.2000-01-02_00.00.00.nc'
        )

        step.add_namelist_file(
            package='polaris.tasks.seaice.single_column.exact_restart',
            namelist='namelist.restart',
        )
        step.add_streams_file(
            package='polaris.tasks.seaice.single_column.exact_restart',
            streams='streams.restart',
        )
        self.add_step(step)

        subdirs = ['full_run', 'restart_run']
        restart_filename = 'restarts/restart.2000-01-02_00.00.00.nc'
        self.add_step(
            Validate(
                component=component,
                step_subdirs=subdirs,
                indir=self.subdir,
                variables=validate_vars,
                restart_filename=restart_filename,
            )
        )
