from polaris import Step
from polaris.validate import compare_variables

OUTPUT_VARIABLES = [
    'temperature',
    'salinity',
    'layerThickness',
    'normalVelocity',
]

LAND_ICE_VARIABLES = [
    'ssh',
    'landIcePressure',
    'landIceDraft',
    'landIceFraction',
    'landIceMask',
    'landIceFrictionVelocity',
    'topDrag',
    'topDragMagnitude',
    'landIceFreshwaterFlux',
    'landIceHeatFlux',
    'heatFluxToLandIce',
    'landIceBoundaryLayerTemperature',
    'landIceBoundaryLayerSalinity',
    'landIceHeatTransferVelocity',
    'landIceSaltTransferVelocity',
    'landIceInterfaceTemperature',
    'landIceInterfaceSalinity',
    'accumulatedLandIceMass',
    'accumulatedLandIceHeat',
]


class Validate(Step):
    """
    A step for checking that a run restarted halfway matches the full run
    in an ISOMIP+ restart test

    Attributes
    ----------
    step_subdirs : list of str
        The steps to compare: the full run and the restart run
    """

    def __init__(self, component, step_subdirs, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            The steps to compare: the full run and the restart run

        indir : str
            The directory the step is in, to which ``validate`` will be
            appended
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs

        for subdir in step_subdirs:
            self.add_input_file(
                filename=f'output_{subdir}.nc', target=f'../{subdir}/output.nc'
            )
            self.add_input_file(
                filename=f'land_ice_fluxes_{subdir}.nc',
                target=f'../{subdir}/land_ice_fluxes.nc',
            )

    def run(self):
        """
        Compare the ocean state and land-ice fluxes at the end of the full
        run and of the restart run
        """
        super().run()
        full, restart = self.step_subdirs
        passed = True
        for prefix, variables in [
            ('output', OUTPUT_VARIABLES),
            ('land_ice_fluxes', LAND_ICE_VARIABLES),
        ]:
            passed = (
                compare_variables(
                    component=self.component,
                    variables=variables,
                    filename1=f'{prefix}_{full}.nc',
                    filename2=f'{prefix}_{restart}.nc',
                    logger=self.logger,
                    config=self.config,
                )
                and passed
            )
        if not passed:
            raise ValueError(
                f'Validation failed comparing outputs between {full} and '
                f'{restart}.'
            )
