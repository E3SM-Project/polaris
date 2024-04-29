from polaris import Step
from polaris.validate import compare_variables


class Validate(Step):
    """
    A step for comparing outputs between steps in a ice shelf 2d run

    Attributes
    ----------
    step_subdirs : list of str
        The steps to be compared (full run and restart run)
    """
    def __init__(self, component, step_subdirs, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            The steps to be compared (full run and restart run)

        indir : str
            the directory the step is in, to which ``validate`` will be
            appended
       """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs

        for subdir in step_subdirs:
            self.add_input_file(filename=f'output_{subdir}.nc',
                                target=f'../{subdir}/output.nc')
            self.add_input_file(filename=f'land_ice_fluxes_{subdir}.nc',
                                target=f'../{subdir}/land_ice_fluxes.nc')
            self.add_input_file(filename=f'frazil_{subdir}.nc',
                                target=f'../{subdir}/frazil.nc')

    def run(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the outputs of two previous steps with each other
        """
        super().run()
        step_subdirs = self.step_subdirs
        output_variables = ['temperature', 'salinity', 'layerThickness',
                            'normalVelocity']
        land_ice_variables = ['ssh', 'landIcePressure', 'landIceDraft',
                              'landIceFraction',
                              'landIceMask', 'landIceFrictionVelocity',
                              'topDrag', 'topDragMagnitude',
                              'landIceFreshwaterFlux', 'landIceHeatFlux',
                              'heatFluxToLandIce',
                              'landIceBoundaryLayerTemperature',
                              'landIceBoundaryLayerSalinity',
                              'landIceHeatTransferVelocity',
                              'landIceSaltTransferVelocity',
                              'landIceInterfaceTemperature',
                              'landIceInterfaceSalinity',
                              'accumulatedLandIceMass',
                              'accumulatedLandIceHeat']
        frazil_variables = ['accumulatedFrazilIceMass',
                            'accumulatedFrazilIceSalinity',
                            'seaIceEnergy', 'frazilLayerThicknessTendency',
                            'frazilTemperatureTendency',
                            'frazilSalinityTendency',
                            'frazilSurfacePressure',
                            'accumulatedLandIceFrazilMass']
        output_pass = compare_variables(variables=output_variables,
                                        filename1=self.inputs[0],
                                        filename2=self.inputs[3],
                                        logger=self.logger)
        land_ice_pass = compare_variables(variables=land_ice_variables,
                                          filename1=self.inputs[1],
                                          filename2=self.inputs[4],
                                          logger=self.logger)
        frazil_pass = compare_variables(variables=frazil_variables,
                                        filename1=self.inputs[2],
                                        filename2=self.inputs[5],
                                        logger=self.logger)
        if not output_pass:
            raise ValueError(f'Validation failed comparing outputs between '
                             f'{step_subdirs[0]} and {step_subdirs[3]}.')
        if not land_ice_pass:
            raise ValueError(f'Validation failed comparing outputs between '
                             f'{step_subdirs[1]} and {step_subdirs[4]}.')
        if not frazil_pass:
            raise ValueError(f'Validation failed comparing outputs between '
                             f'{step_subdirs[2]} and {step_subdirs[5]}.')
