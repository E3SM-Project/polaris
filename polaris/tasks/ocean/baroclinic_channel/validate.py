from polaris import Step
from polaris.validate import compare_variables


class Validate(Step):
    """
    A step for comparing outputs between steps in a baroclinic channel run

    Attributes
    ----------
    step_subdirs : list of str
        The number of processors used in each run
    """

    def __init__(self, component, step_subdirs, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            The number of processors used in each run

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs

        for subdir in step_subdirs:
            self.add_input_file(
                filename=f'output_{subdir}.nc', target=f'../{subdir}/output.nc'
            )

    def run(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the outputs of two previous steps with each other
        """
        super().run()
        step_subdirs = self.step_subdirs
        variables = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        all_pass = compare_variables(
            component=self.component,
            variables=variables,
            filename1=self.inputs[0],
            filename2=self.inputs[1],
            logger=self.logger,
        )
        if not all_pass:
            raise ValueError(
                f'Validation failed comparing outputs between '
                f'{step_subdirs[0]} and {step_subdirs[1]}.'
            )
