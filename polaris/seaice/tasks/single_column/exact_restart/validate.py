from polaris import Step
from polaris.validate import compare_variables


class Validate(Step):
    """
    A step for comparing outputs between steps in a single-column restart run

    Attributes
    ----------
    step_subdirs : list of str
        The number of processors used in each run

    variables : list of str
        The variables to validate
    """

    def __init__(
        self, component, step_subdirs, indir, variables, restart_filename
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            The number of processors used in each run

        indir : str
            the directory the step is in, to which the name of the step will
            be appended

        variables : list of str
            The variables to validate

        restart_filename : str
            The relative path to the restart file to compare in the 2 subdirs
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs

        for subdir in step_subdirs:
            self.add_input_file(
                filename=f'{subdir}_restart.nc',
                target=f'../{subdir}/{restart_filename}',
            )

        self.variables = variables

    def run(self):
        """
        Compare the variables in the outputs of two previous steps with each
        other
        """
        super().run()
        step_subdirs = self.step_subdirs
        all_pass = compare_variables(
            variables=self.variables,
            filename1=self.inputs[0],
            filename2=self.inputs[1],
            logger=self.logger,
        )
        if not all_pass:
            raise ValueError(
                f'Validation failed comparing restart between '
                f'{step_subdirs[0]} and {step_subdirs[1]}.'
            )
